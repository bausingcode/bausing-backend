from flask import Blueprint, request, jsonify
from database import db
from models.user import User
from models.referral import Referral
from models.order import Order
from models.settings import SystemSettings
from models.wallet import Wallet, WalletMovement
from routes.auth import user_required
from routes.admin_auth import admin_required
from sqlalchemy import func, desc
from datetime import datetime
import uuid

referrals_bp = Blueprint('referrals', __name__)

def get_or_create_wallet(user_id):
    """Obtener o crear wallet para un usuario"""
    wallet = Wallet.query.filter_by(user_id=user_id).first()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0.00, is_blocked=False)
        db.session.add(wallet)
        db.session.flush()
    return wallet

def calculate_referral_credit(order_total, credit_type, credit_amount, percentage):
    """Calcula el monto de crédito según la configuración"""
    if credit_type == 'fixed':
        return float(credit_amount)
    elif credit_type == 'percentage':
        return float(order_total) * (float(percentage) / 100.0)
    else:
        return 0.0

def validate_referral_code_logic(code, user_id=None):
    """
    Lógica de validación de código de referido (reutilizable)
    Retorna dict con 'valid' (bool) y 'message' (str)
    """
    if not code:
        return {'valid': False, 'message': 'Código requerido'}
    
    code = code.strip().upper()
    
    # Buscar usuario con ese código
    referrer = User.query.filter_by(referral_code=code).first()
    
    if not referrer:
        return {'valid': False, 'message': 'Código de referido no encontrado'}
    
    # Verificar que no esté suspendido
    if referrer.is_suspended:
        return {'valid': False, 'message': 'Este código de referido no está disponible'}
    
    # Si hay user_id, verificar que no sea su propio código
    if user_id and referrer.id == user_id:
        return {'valid': False, 'message': 'No puedes usar tu propio código de referido'}
    
    return {'valid': True, 'message': 'Código válido', 'referrer': referrer}

def process_referral_credit(order):
    """
    Procesa el crédito de referido cuando una orden es finalizada.
    Se llama cuando order.payment_processed = True y order.referral_code_used IS NOT NULL
    """
    if not order.referral_code_used:
        return None
    
    # Verificar si ya se procesó este referido
    existing_referral = Referral.query.filter_by(order_id=order.id).first()
    if existing_referral and existing_referral.credited:
        return existing_referral
    
    # Buscar el referidor por código
    referrer = User.query.filter_by(referral_code=order.referral_code_used).first()
    if not referrer:
        print(f"[REFERRAL] Código de referido no encontrado: {order.referral_code_used}")
        return None
    
    # Verificar que el referidor no esté suspendido
    if referrer.is_suspended:
        print(f"[REFERRAL] Referidor suspendido: {referrer.id}")
        return None
    
    # Verificar que no sea auto-referido
    if referrer.id == order.user_id:
        print(f"[REFERRAL] Intento de auto-referido detectado: {order.user_id}")
        return None
    
    # Obtener configuración
    credit_type_setting = SystemSettings.get_value('referral.credit_type', default='fixed')
    credit_amount_setting = SystemSettings.get_value('referral.credit_amount', default=500.0)
    percentage_setting = SystemSettings.get_value('referral.percentage', default=5.0)
    
    # Calcular monto de crédito
    credit_amount = calculate_referral_credit(
        order.total,
        credit_type_setting,
        credit_amount_setting,
        percentage_setting
    )
    
    if credit_amount <= 0:
        print(f"[REFERRAL] Monto de crédito inválido: {credit_amount}")
        return None
    
    # Crear registro de referido
    referral = Referral(
        referrer_id=referrer.id,
        referred_id=order.user_id,
        order_id=order.id,
        credit_amount=credit_amount,
        credited=False
    )
    db.session.add(referral)
    db.session.flush()
    
    # Obtener o crear wallet del referidor
    wallet = get_or_create_wallet(referrer.id)
    
    # Crear movimiento de wallet
    wallet_movement = WalletMovement(
        wallet_id=wallet.id,
        type='referral_credit',
        amount=credit_amount,
        description=f'Crédito por referido - Orden #{str(order.id)[:8]}',
        order_id=order.id
    )
    db.session.add(wallet_movement)
    db.session.flush()
    
    # Actualizar balance de wallet
    from routes.wallet import calculate_wallet_balance
    wallet.balance = calculate_wallet_balance(wallet.id, include_expired=False)
    wallet.updated_at = datetime.utcnow()
    
    # Marcar como acreditado
    referral.credited = True
    referral.credited_at = datetime.utcnow()
    
    db.session.commit()
    
    print(f"[REFERRAL] ✅ Crédito acreditado: ${credit_amount} a usuario {referrer.id} por orden {order.id}")
    
    return referral

# ============================================
# Endpoints públicos/autenticados
# ============================================

@referrals_bp.route('/referrals/my-code', methods=['GET'])
@user_required
def get_my_referral_code():
    """Obtener o generar código de referido del usuario autenticado"""
    try:
        user = request.user
        
        # Si no tiene código, generarlo
        if not user.referral_code:
            user.referral_code = User.generate_referral_code()
            db.session.commit()
        
        return jsonify({
            'success': True,
            'data': {
                'referral_code': user.referral_code
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Error al obtener código de referido: {str(e)}'
        }), 500

@referrals_bp.route('/referrals/validate', methods=['POST'])
def validate_referral_code():
    """
    Validar código de referido (público, no requiere autenticación)
    Útil para validar en tiempo real en el checkout
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400
        
        code = data.get('code', '').strip().upper()
        
        if not code:
            return jsonify({
                'success': False,
                'error': 'Código requerido',
                'valid': False
            }), 400
        
        # Buscar usuario con ese código
        referrer = User.query.filter_by(referral_code=code).first()
        
        if not referrer:
            return jsonify({
                'success': True,
                'valid': False,
                'message': 'Código de referido no encontrado'
            }), 200
        
        # Verificar que no esté suspendido
        if referrer.is_suspended:
            return jsonify({
                'success': True,
                'valid': False,
                'message': 'Este código de referido no está disponible'
            }), 200
        
        # Si hay usuario autenticado, verificar que no sea su propio código
        user_id = None
        if 'Authorization' in request.headers:
            try:
                from routes.auth import verify_token
                auth_header = request.headers['Authorization']
                token = auth_header.split(' ')[1]
                payload = verify_token(token)
                if payload:
                    user_id = uuid.UUID(payload['user_id'])
            except:
                pass
        
        if user_id and referrer.id == user_id:
            return jsonify({
                'success': True,
                'valid': False,
                'message': 'No puedes usar tu propio código de referido'
            }), 200
        
        return jsonify({
            'success': True,
            'valid': True,
            'message': 'Código válido'
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error al validar código: {str(e)}'
        }), 500

@referrals_bp.route('/referrals/stats', methods=['GET'])
@user_required
def get_referral_stats():
    """Obtener estadísticas de referidos del usuario autenticado"""
    try:
        user = request.user
        
        # Total de referidos
        total_referrals = Referral.query.filter_by(referrer_id=user.id).count()
        
        # Total de créditos ganados
        total_credits = db.session.query(func.coalesce(func.sum(Referral.credit_amount), 0)).filter(
            Referral.referrer_id == user.id,
            Referral.credited == True
        ).scalar() or 0
        
        # Referidos que ya generaron crédito
        credited_referrals = Referral.query.filter_by(
            referrer_id=user.id,
            credited=True
        ).count()
        
        # Referidos pendientes (aún no acreditados)
        pending_referrals = Referral.query.filter_by(
            referrer_id=user.id,
            credited=False
        ).count()
        
        return jsonify({
            'success': True,
            'data': {
                'total_referrals': total_referrals,
                'total_credits': float(total_credits),
                'credited_referrals': credited_referrals,
                'pending_referrals': pending_referrals,
                'referral_code': user.referral_code
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error al obtener estadísticas: {str(e)}'
        }), 500

@referrals_bp.route('/referrals/history', methods=['GET'])
@user_required
def get_referral_history():
    """Obtener historial de referidos del usuario autenticado"""
    try:
        user = request.user
        
        # Obtener parámetros de paginación
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)  # Máximo 100 por página
        
        # Obtener referidos con paginación
        referrals_query = Referral.query.filter_by(referrer_id=user.id).order_by(
            desc(Referral.created_at)
        )
        
        pagination = referrals_query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        referrals = [ref.to_dict(include_users=True) for ref in pagination.items]
        
        return jsonify({
            'success': True,
            'data': {
                'referrals': referrals,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': pagination.total,
                    'pages': pagination.pages
                }
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error al obtener historial: {str(e)}'
        }), 500

# ============================================
# Endpoints de administración
# ============================================

@referrals_bp.route('/admin/referrals/config', methods=['GET'])
@admin_required
def get_referral_config():
    """Obtener configuración del programa de referidos (admin)"""
    try:
        credit_type = SystemSettings.get_value('referral.credit_type', default='fixed')
        credit_amount = SystemSettings.get_value('referral.credit_amount', default=500.0)
        percentage = SystemSettings.get_value('referral.percentage', default=5.0)
        
        return jsonify({
            'success': True,
            'data': {
                'credit_type': credit_type,
                'credit_amount': float(credit_amount),
                'percentage': float(percentage)
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error al obtener configuración: {str(e)}'
        }), 500

@referrals_bp.route('/admin/referrals/config', methods=['PUT'])
@admin_required
def update_referral_config():
    """Actualizar configuración del programa de referidos (admin)"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400
        
        credit_type = data.get('credit_type')
        credit_amount = data.get('credit_amount')
        percentage = data.get('percentage')
        
        if credit_type not in ['fixed', 'percentage']:
            return jsonify({
                'success': False,
                'error': 'credit_type debe ser "fixed" o "percentage"'
            }), 400
        
        # Actualizar configuración
        if credit_type:
            SystemSettings.set_value(
                key='referral.credit_type',
                value=credit_type,
                value_type='string',
                category='referral',
                description='Tipo de crédito: fixed o percentage',
                updated_by=request.admin_user.id
            )
        
        if credit_amount is not None:
            if credit_amount < 0:
                return jsonify({
                    'success': False,
                    'error': 'credit_amount debe ser mayor o igual a 0'
                }), 400
            
            SystemSettings.set_value(
                key='referral.credit_amount',
                value=float(credit_amount),
                value_type='number',
                category='referral',
                description='Monto fijo de crédito por referido',
                updated_by=request.admin_user.id
            )
        
        if percentage is not None:
            if percentage < 0 or percentage > 100:
                return jsonify({
                    'success': False,
                    'error': 'percentage debe estar entre 0 y 100'
                }), 400
            
            SystemSettings.set_value(
                key='referral.percentage',
                value=float(percentage),
                value_type='number',
                category='referral',
                description='Porcentaje del total si credit_type es percentage',
                updated_by=request.admin_user.id
            )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Configuración actualizada correctamente'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Error al actualizar configuración: {str(e)}'
        }), 500

@referrals_bp.route('/admin/referrals/stats', methods=['GET'])
@admin_required
def get_admin_referral_stats():
    """Obtener estadísticas generales del programa de referidos (admin)"""
    try:
        # Total de referidos
        total_referrals = Referral.query.count()
        
        # Total de créditos otorgados
        total_credits = db.session.query(func.coalesce(func.sum(Referral.credit_amount), 0)).filter(
            Referral.credited == True
        ).scalar() or 0
        
        # Referidos acreditados
        credited_referrals = Referral.query.filter_by(credited=True).count()
        
        # Referidos pendientes
        pending_referrals = Referral.query.filter_by(credited=False).count()
        
        # Top referidores (top 10)
        top_referrers = db.session.query(
            User.id,
            User.first_name,
            User.last_name,
            User.email,
            func.count(Referral.id).label('total_referrals'),
            func.coalesce(func.sum(Referral.credit_amount), 0).label('total_credits')
        ).join(
            Referral, User.id == Referral.referrer_id
        ).filter(
            Referral.credited == True
        ).group_by(
            User.id, User.first_name, User.last_name, User.email
        ).order_by(
            desc('total_credits')
        ).limit(10).all()
        
        top_referrers_list = []
        for ref in top_referrers:
            top_referrers_list.append({
                'user_id': str(ref.id),
                'first_name': ref.first_name,
                'last_name': ref.last_name,
                'email': ref.email,
                'total_referrals': ref.total_referrals,
                'total_credits': float(ref.total_credits)
            })
        
        return jsonify({
            'success': True,
            'data': {
                'total_referrals': total_referrals,
                'total_credits': float(total_credits),
                'credited_referrals': credited_referrals,
                'pending_referrals': pending_referrals,
                'top_referrers': top_referrers_list
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error al obtener estadísticas: {str(e)}'
        }), 500
