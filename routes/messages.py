"""
Rutas para el envío de mensajes masivos y recordatorios
"""
from flask import Blueprint, request, jsonify
from database import db
from models.user import User
from models.wallet import Wallet, WalletMovement
from routes.admin import admin_required
from utils.email_service import email_service
from config import Config
from datetime import datetime, timedelta
from sqlalchemy import and_, or_, func
from decimal import Decimal
import re

messages_bp = Blueprint('messages', __name__)


@messages_bp.route('/admin/messages/promotional', methods=['POST'])
@admin_required
def send_promotional_emails():
    """
    Envía mensajes promocionales a usuarios según el filtro seleccionado.
    
    Body:
    {
        "subject": "Asunto del email",
        "message": "Contenido del mensaje. Puede usar {{nombre}} para personalizar.",
        "user_filter": "all" | "with_orders" | "without_orders" | "with_wallet" | "with_wallet_balance" | "verified" | "recent"
    }
    """
    try:
        from models.order import Order
        
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400
        
        subject = data.get('subject', '').strip()
        message = data.get('message', '').strip()
        user_filter = data.get('user_filter', 'all')
        
        if not subject:
            return jsonify({
                'success': False,
                'error': 'El asunto es requerido'
            }), 400
        
        if not message:
            return jsonify({
                'success': False,
                'error': 'El mensaje es requerido'
            }), 400
        
        # Base query: usuarios con email
        query = User.query.filter(
            User.email.isnot(None),
            User.email != ''
        )
        
        # Aplicar filtros según la opción seleccionada
        if user_filter == 'with_orders':
            # Usuarios con al menos una orden
            query = query.join(Order, User.id == Order.user_id).distinct()
        elif user_filter == 'without_orders':
            # Usuarios sin órdenes
            users_with_orders_subq = db.session.query(Order.user_id).distinct()
            query = query.filter(~User.id.in_(users_with_orders_subq))
        elif user_filter == 'with_wallet':
            # Usuarios con billetera (aunque tenga saldo 0)
            query = query.join(Wallet, User.id == Wallet.user_id)
        elif user_filter == 'with_wallet_balance':
            # Usuarios con saldo mayor a 0
            query = query.join(Wallet, User.id == Wallet.user_id).filter(Wallet.balance > 0)
        elif user_filter == 'verified':
            # Usuarios con email verificado
            query = query.filter(User.email_verified == True)
        elif user_filter == 'recent':
            # Usuarios registrados en los últimos 30 días
            from datetime import datetime, timedelta
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            query = query.filter(User.created_at >= thirty_days_ago)
        # 'all' no necesita filtro adicional
        
        users = query.all()
        
        if not users:
            return jsonify({
                'success': False,
                'error': 'No hay usuarios con email registrados'
            }), 404
        
        sent_count = 0
        failed_count = 0
        
        # Enviar email a cada usuario
        for user in users:
            try:
                # Personalizar el mensaje
                personalized_message = message.replace('{{nombre}}', user.first_name)
                
                # Convertir saltos de línea a HTML
                personalized_message_html = personalized_message.replace('\n', '<br>')
                
                # Enviar email usando el servicio
                # No agregamos greeting automático, el usuario puede personalizarlo en el mensaje
                success = email_service.send_custom_email(
                    to=user.email,
                    title=subject,
                    header_text=subject,
                    greeting="",  # Sin saludo automático, el usuario lo incluye en el mensaje
                    main_content=personalized_message_html,
                    button_text="Ver productos",
                    button_url=f"{Config.FRONTEND_URL}/productos" if Config.FRONTEND_URL else None,
                    footer_note="Este es un mensaje promocional de Bausing."
                )
                
                if success:
                    sent_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                print(f"Error al enviar email a {user.email}: {str(e)}")
                failed_count += 1
        
        return jsonify({
            'success': True,
            'sent_count': sent_count,
            'failed_count': failed_count,
            'total_users': len(users),
            'message': f'Se enviaron {sent_count} emails exitosamente'
        }), 200
        
    except Exception as e:
        print(f"Error en send_promotional_emails: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error al enviar los mensajes: {str(e)}'
        }), 500


@messages_bp.route('/admin/messages/wallet-reminders', methods=['POST'])
@admin_required
def send_wallet_reminders():
    """
    Envía recordatorios de billetera a usuarios con saldo que vence próximamente.
    Considera saldo que vence en los próximos 7 días.
    """
    try:
        # Calcular fecha límite (7 días desde ahora)
        now = datetime.utcnow()
        days_ahead = 7
        expiration_limit = now + timedelta(days=days_ahead)
        
        # Obtener usuarios con movimientos de crédito que vencen próximamente
        # Buscamos movimientos de crédito que:
        # 1. Tienen expires_at (no son None)
        # 2. Vencen entre ahora y 7 días
        # 3. Aún no han vencido (expires_at > now)
        # 4. Son movimientos de crédito (suman dinero)
        credit_types = ['manual_credit', 'cashback', 'refund', 'transfer_in', 'accreditation', 'credit']
        
        # Query para obtener usuarios con saldo próximo a vencer
        # Agrupamos por usuario y calculamos el saldo total que vence pronto
        upcoming_expirations = db.session.query(
            User.id,
            User.email,
            User.first_name,
            User.last_name,
            func.sum(WalletMovement.amount).label('expiring_balance')
        ).join(
            Wallet, User.id == Wallet.user_id
        ).join(
            WalletMovement, Wallet.id == WalletMovement.wallet_id
        ).filter(
            and_(
                User.email.isnot(None),
                User.email != '',
                WalletMovement.type.in_(credit_types),
                WalletMovement.amount > 0,
                WalletMovement.expires_at.isnot(None),
                WalletMovement.expires_at > now,
                WalletMovement.expires_at <= expiration_limit
            )
        ).group_by(
            User.id, User.email, User.first_name, User.last_name
        ).having(
            func.sum(WalletMovement.amount) > 0
        ).all()
        
        if not upcoming_expirations:
            return jsonify({
                'success': True,
                'sent_count': 0,
                'message': 'No hay usuarios con saldo próximo a vencer'
            }), 200
        
        sent_count = 0
        failed_count = 0
        
        # Enviar recordatorio a cada usuario
        for user_id, email, first_name, last_name, expiring_balance in upcoming_expirations:
            try:
                # Formatear el saldo (convertir Decimal a float y formatear en formato argentino)
                balance_value = float(expiring_balance) if isinstance(expiring_balance, Decimal) else float(expiring_balance)
                # Formato argentino: $1.234,56
                balance_str = f"${balance_value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                
                # Obtener la fecha de vencimiento más próxima para este usuario
                earliest_expiration = db.session.query(
                    func.min(WalletMovement.expires_at)
                ).join(
                    Wallet, WalletMovement.wallet_id == Wallet.id
                ).filter(
                    and_(
                        Wallet.user_id == user_id,
                        WalletMovement.type.in_(credit_types),
                        WalletMovement.amount > 0,
                        WalletMovement.expires_at.isnot(None),
                        WalletMovement.expires_at > now,
                        WalletMovement.expires_at <= expiration_limit
                    )
                ).scalar()
                
                # Calcular días hasta el vencimiento
                if earliest_expiration:
                    days_until_expiry = (earliest_expiration - now).days
                    if days_until_expiry == 0:
                        expiry_text = "hoy"
                    elif days_until_expiry == 1:
                        expiry_text = "mañana"
                    else:
                        expiry_text = f"en {days_until_expiry} días"
                else:
                    expiry_text = "próximamente"
                
                # Crear el mensaje personalizado
                main_content = f"""
                <p>Tenés saldo en tu billetera Bausing que vence {expiry_text}.</p>
                <p><strong>Saldo próximo a vencer: {balance_str}</strong></p>
                <p>Te recomendamos que utilices tu saldo antes de que expire. Podés usarlo para realizar compras en nuestra tienda.</p>
                <p>¡No dejes que se venza tu saldo!</p>
                """
                
                # Enviar email
                success = email_service.send_custom_email(
                    to=email,
                    title="Recordatorio: Tu saldo de billetera vence pronto",
                    header_text="Recordatorio de Billetera",
                    greeting=f"Hola {first_name},",
                    main_content=main_content,
                    button_text="Ver mi billetera",
                    button_url=f"{Config.FRONTEND_URL}/billetera" if Config.FRONTEND_URL else None,
                    footer_note="Este es un recordatorio automático de Bausing."
                )
                
                if success:
                    sent_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                print(f"Error al enviar recordatorio a {email}: {str(e)}")
                failed_count += 1
        
        return jsonify({
            'success': True,
            'sent_count': sent_count,
            'failed_count': failed_count,
            'total_users': len(upcoming_expirations),
            'message': f'Se enviaron {sent_count} recordatorios exitosamente'
        }), 200
        
    except Exception as e:
        print(f"Error en send_wallet_reminders: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Error al enviar los recordatorios: {str(e)}'
        }), 500
