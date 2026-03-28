from flask import Blueprint, request, jsonify, Response
from database import db
from models.user import User
from models.wallet import Wallet, WalletMovement, AuditLog
from models.admin_user import AdminUser
from models.settings import SystemSettings
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, and_, func, desc
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta
import uuid
import csv
import io
from routes.admin import admin_required
from routes.auth import user_required

wallet_bp = Blueprint('wallet', __name__)

# Helper function to get or create wallet
def get_or_create_wallet(user_id):
    """Obtiene o crea una billetera para un usuario"""
    wallet = Wallet.query.filter_by(user_id=user_id).first()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0.00, is_blocked=False)
        db.session.add(wallet)
        db.session.flush()
    return wallet

# Helper function to calculate expiration date for wallet movements
def calculate_expiration_date(created_at=None):
    """
    Calcula la fecha de vencimiento para un movimiento de wallet basado en la configuración del sistema.
    Solo aplica para movimientos de crédito (cashback, manual_credit, transfer_in, etc.)
    
    Returns:
        datetime o None si no hay configuración de vencimiento
    """
    if created_at is None:
        created_at = datetime.utcnow()
    
    # Obtener días de vencimiento desde la configuración
    expiration_days = SystemSettings.get_value('wallet.expiration_days', default=None)
    
    if expiration_days is None or expiration_days <= 0:
        return None
    
    # Calcular fecha de vencimiento sumando los días configurados
    expires_at = created_at + timedelta(days=int(expiration_days))
    return expires_at

# Helper function to calculate wallet balance excluding expired movements
def calculate_wallet_balance(wallet_id, include_expired=False):
    """
    Calcula el balance de una wallet excluyendo movimientos vencidos.
    Solo cuenta movimientos de crédito que no hayan vencido.
    
    Tipos de movimientos que RESTAN (débitos):
    - manual_debit, order_payment, purchase, payment, transfer_out
    
    Tipos de movimientos que SUMAN (créditos):
    - manual_credit, cashback, refund, transfer_in, accreditation
    
    Args:
        wallet_id: ID de la wallet
        include_expired: Si es True, incluye créditos vencidos (para cálculos internos)
    
    Returns:
        Balance calculado (Decimal)
    """
    now = datetime.utcnow()
    
    # Tipos que son débitos (restan dinero)
    debit_types = ['manual_debit', 'order_payment', 'purchase', 'payment', 'transfer_out']
    # Tipos que son créditos (suman dinero)
    credit_types = ['manual_credit', 'cashback', 'refund', 'transfer_in', 'accreditation', 'credit', 'referral_credit']
    
    if include_expired:
        # Sumar TODOS los créditos (incluidos vencidos)
        credits = db.session.query(func.coalesce(func.sum(WalletMovement.amount), 0)).filter(
            WalletMovement.wallet_id == wallet_id,
            WalletMovement.type.in_(credit_types),
            WalletMovement.amount > 0  # Solo créditos positivos
        ).scalar() or 0
        
        # Sumar todos los débitos (pueden ser positivos o negativos según cómo se guardaron)
        debits_query = db.session.query(func.coalesce(func.sum(WalletMovement.amount), 0)).filter(
            WalletMovement.wallet_id == wallet_id,
            WalletMovement.type.in_(debit_types)
        )
        # Si el amount es positivo, hacerlo negativo; si ya es negativo, dejarlo así
        debits = debits_query.scalar() or 0
        # Si hay débitos con amount positivo (error histórico), convertirlos a negativo
        positive_debits = db.session.query(func.coalesce(func.sum(WalletMovement.amount), 0)).filter(
            WalletMovement.wallet_id == wallet_id,
            WalletMovement.type.in_(debit_types),
            WalletMovement.amount > 0
        ).scalar() or 0
        negative_debits = db.session.query(func.coalesce(func.sum(WalletMovement.amount), 0)).filter(
            WalletMovement.wallet_id == wallet_id,
            WalletMovement.type.in_(debit_types),
            WalletMovement.amount < 0
        ).scalar() or 0
        debits = negative_debits - positive_debits  # Restar los positivos (convertirlos a negativos)
    else:
        # Sumar solo créditos que NO hayan vencido
        credits = db.session.query(func.coalesce(func.sum(WalletMovement.amount), 0)).filter(
            WalletMovement.wallet_id == wallet_id,
            WalletMovement.type.in_(credit_types),
            WalletMovement.amount > 0,  # Solo créditos positivos
            or_(
                WalletMovement.expires_at.is_(None),  # Sin vencimiento
                WalletMovement.expires_at > now  # No vencidos
            )
        ).scalar() or 0
        
        # Sumar todos los débitos (convertir positivos a negativos)
        positive_debits = db.session.query(func.coalesce(func.sum(WalletMovement.amount), 0)).filter(
            WalletMovement.wallet_id == wallet_id,
            WalletMovement.type.in_(debit_types),
            WalletMovement.amount > 0
        ).scalar() or 0
        negative_debits = db.session.query(func.coalesce(func.sum(WalletMovement.amount), 0)).filter(
            WalletMovement.wallet_id == wallet_id,
            WalletMovement.type.in_(debit_types),
            WalletMovement.amount < 0
        ).scalar() or 0
        debits = negative_debits - positive_debits  # Restar los positivos (convertirlos a negativos)
    
    # El balance es créditos válidos más débitos (débitos ya son negativos)
    balance = credits + debits
    
    return balance

# Helper function to create audit log
def create_audit_log(admin_user_id, action, entity, entity_id, details=None):
    """Crea un log de auditoría"""
    try:
        # Verificar que el admin_user existe
        admin_user = AdminUser.query.get(admin_user_id)
        if not admin_user:
            raise ValueError(f"Admin user {admin_user_id} no encontrado")
        
        # Verificar la estructura del modelo AuditLog
        
        audit_log = AuditLog(
            user_id=admin_user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details or {}
        )
        
        db.session.add(audit_log)
        
        # Intentar flush para ver si hay error inmediatamente
        db.session.flush()
        
        return audit_log
    except IntegrityError as e:
        raise
    except Exception as e:
        raise


# 5.1. BUSCADOR CENTRAL DE CLIENTES
@wallet_bp.route('/admin/wallet/customers/search', methods=['GET'])
@admin_required
def search_customers():
    """
    Buscar clientes por nombre, teléfono, email o DNI
    
    Query parameters:
    - q: término de búsqueda
    - limit: límite de resultados (default: 20)
    """
    try:
        import traceback
        
        search_query = request.args.get('q', '').strip()
        limit = min(request.args.get('limit', 20, type=int), 100)

        if not search_query:
            return jsonify({
                'success': False,
                'error': 'Término de búsqueda requerido'
            }), 400

        # Buscar por nombre, teléfono, email o DNI
        try:
            users = User.query.filter(
                or_(
                    User.first_name.ilike(f'%{search_query}%'),
                    User.last_name.ilike(f'%{search_query}%'),
                    User.email.ilike(f'%{search_query}%'),
                    User.phone.ilike(f'%{search_query}%'),
                    User.dni.ilike(f'%{search_query}%')
                )
            ).limit(limit).all()
        except Exception as query_error:
            raise

        results = []
        for idx, user in enumerate(users):
            try:
                wallet = Wallet.query.filter_by(user_id=user.id).first()
                
                wallet_balance = 0.0
                wallet_blocked = False
                if wallet:
                    try:
                        # Usar el balance guardado en la DB (ya excluye créditos vencidos)
                        wallet_balance = float(wallet.balance) if wallet.balance else 0.0
                        wallet_blocked = wallet.is_blocked if hasattr(wallet, 'is_blocked') else False
                    except Exception:
                        wallet_balance = 0.0
                        wallet_blocked = False
                
                results.append({
                    'id': str(user.id),
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'email': user.email,
                    'phone': user.phone,
                    'dni': user.dni,
                    'has_wallet': wallet is not None,
                    'wallet_balance': wallet_balance,
                    'wallet_blocked': wallet_blocked
                })
            except Exception as user_error:
                # Continuar con el siguiente usuario aunque uno falle
                continue

        return jsonify({
            'success': True,
            'data': results
        }), 200

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': error_trace
        }), 500


@wallet_bp.route('/admin/wallet/customers/<uuid:user_id>/summary', methods=['GET'])
@admin_required
def get_customer_wallet_summary(user_id):
    """
    Obtener resumen de billetera del cliente:
    - Saldo actual
    - Último uso de la billetera
    """
    try:
        user = User.query.get_or_404(user_id)
        wallet = get_or_create_wallet(user_id)

        # Obtener último movimiento
        last_movement = WalletMovement.query.filter_by(wallet_id=wallet.id).order_by(desc(WalletMovement.created_at)).first()

        # Usar el balance guardado en la DB (ya excluye créditos vencidos)
        return jsonify({
            'success': True,
            'data': {
                'user': {
                    'id': str(user.id),
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'email': user.email,
                    'phone': user.phone,
                    'dni': user.dni
                },
                'wallet': {
                    'balance': float(wallet.balance) if wallet.balance else 0.0,
                    'is_blocked': wallet.is_blocked,
                    'last_movement': {
                        'id': str(last_movement.id),
                        'type': last_movement.type,
                        'amount': float(last_movement.amount) if last_movement.amount else 0.0,
                        'description': last_movement.description,
                        'created_at': last_movement.created_at.isoformat() if last_movement.created_at else None
                    } if last_movement else None
                }
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@wallet_bp.route('/admin/wallet/customers/<uuid:user_id>/movements', methods=['GET'])
@admin_required
def get_customer_wallet_movements(user_id):
    """
    Obtener historial de movimientos de billetera del cliente (tipo extracto bancario)
    
    Query parameters:
    - page: número de página (default: 1)
    - per_page: items por página (default: 50)
    - type: filtrar por tipo de movimiento
    """
    try:
        user = User.query.get_or_404(user_id)
        wallet = get_or_create_wallet(user_id)

        # Paginación
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)
        movement_type = request.args.get('type')

        # Query base
        query = WalletMovement.query.filter_by(wallet_id=wallet.id)

        # Filtro por tipo
        if movement_type:
            query = query.filter_by(type=movement_type)

        # Ordenar por fecha descendente
        query = query.order_by(desc(WalletMovement.created_at))

        # Paginación
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        movements = pagination.items

        return jsonify({
            'success': True,
            'data': {
                'movements': [movement.to_dict(include_admin=True) for movement in movements],
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
            'error': str(e)
        }), 500


# 5.2. ACCIONES MANUALES CONTROLADAS
@wallet_bp.route('/admin/wallet/customers/<uuid:user_id>/credit', methods=['POST'])
@admin_required
def manual_credit(user_id):
    """
    Cargar saldo manualmente
    
    Body:
    {
        "amount": 100.00,
        "reason": "promoción",
        "internal_comment": "Promoción de verano",
        "expires_at": "2025-12-31" (opcional, formato YYYY-MM-DD)
    }
    """
    try:
        import traceback
        
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400

        amount = data.get('amount')
        reason = data.get('reason', '')
        internal_comment = data.get('internal_comment', '')
        expires_at_str = data.get('expires_at')  # Fecha de vencimiento opcional (ISO format)

        if not amount or amount <= 0:
            return jsonify({
                'success': False,
                'error': 'El monto debe ser mayor a 0'
            }), 400

        if not reason:
            return jsonify({
                'success': False,
                'error': 'El motivo es requerido'
            }), 400

        user = User.query.get_or_404(user_id)
        
        wallet = get_or_create_wallet(user_id)

        if wallet.is_blocked:
            return jsonify({
                'success': False,
                'error': 'La billetera está bloqueada'
            }), 400

        # Calcular fecha de vencimiento
        # Si se proporciona una fecha personalizada, usarla; si no, usar la configuración del sistema
        if expires_at_str:
            try:
                # Parsear la fecha proporcionada (formato ISO: YYYY-MM-DD)
                expires_at = datetime.strptime(expires_at_str, '%Y-%m-%d')
                # Asegurar que sea al final del día
                expires_at = expires_at.replace(hour=23, minute=59, second=59)
            except ValueError as e:
                return jsonify({
                    'success': False,
                    'error': 'Formato de fecha inválido. Use YYYY-MM-DD'
                }), 400
        else:
            # Usar la configuración del sistema
            expires_at = calculate_expiration_date()
        
        # Crear movimiento (sin admin_user_id, reason, internal_comment porque no existen en BD)
        movement = WalletMovement(
            wallet_id=wallet.id,
            type='manual_credit',
            amount=amount,
            description=f'Carga manual: {reason}',
            expires_at=expires_at
        )
        db.session.add(movement)

        # Actualizar saldo excluyendo créditos vencidos (igual que en el frontend)
        # El balance guardado debe coincidir con el balance mostrado al usuario
        wallet.balance = calculate_wallet_balance(wallet.id, include_expired=False)
        wallet.updated_at = datetime.utcnow()

        # Crear log de auditoría
        
        try:
            create_audit_log(
                admin_user_id=request.admin_user.id,
                action='wallet_manual_credit',
                entity='wallet',
                entity_id=wallet.id,
                details={
                    'user_id': str(user_id),
                    'amount': float(amount),
                    'reason': reason,
                    'internal_comment': internal_comment
                }
            )
        except Exception as audit_error:
            raise

        db.session.commit()

        return jsonify({
            'success': True,
            'data': {
                'wallet': wallet.to_dict(),
                'movement': movement.to_dict()
            }
        }), 200

    except IntegrityError as e:
        import traceback
        error_trace = traceback.format_exc()
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Error de integridad: ' + str(e),
            'traceback': error_trace
        }), 400
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': error_trace
        }), 500


@wallet_bp.route('/admin/wallet/customers/<uuid:user_id>/debit', methods=['POST'])
@admin_required
def manual_debit(user_id):
    """
    Descontar saldo manualmente
    
    Body:
    {
        "amount": 50.00,
        "reason": "fraude",
        "internal_comment": "Ajuste por fraude detectado"
    }
    """
    try:
        import traceback
        
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400

        amount = data.get('amount')
        reason = data.get('reason', '')
        internal_comment = data.get('internal_comment', '')

        if not amount or amount <= 0:
            return jsonify({
                'success': False,
                'error': 'El monto debe ser mayor a 0'
            }), 400

        if not reason:
            return jsonify({
                'success': False,
                'error': 'El motivo es requerido'
            }), 400

        if not internal_comment:
            return jsonify({
                'success': False,
                'error': 'El comentario interno es obligatorio para descuentos'
            }), 400

        user = User.query.get_or_404(user_id)
        
        wallet = get_or_create_wallet(user_id)

        if wallet.is_blocked:
            return jsonify({
                'success': False,
                'error': 'La billetera está bloqueada'
            }), 400

        # Verificar que haya saldo suficiente
        current_balance = wallet.balance or 0
        if current_balance < amount:
            return jsonify({
                'success': False,
                'error': f'Saldo insuficiente. Saldo actual: ${current_balance:.2f}'
            }), 400

        # Crear movimiento (sin admin_user_id, reason, internal_comment porque no existen en BD)
        # Los débitos deben tener amount negativo para que se resten correctamente
        movement = WalletMovement(
            wallet_id=wallet.id,
            type='manual_debit',
            amount=-amount,  # Negativo para que reste del balance
            description=f'Descuento manual: {reason}'
        )
        db.session.add(movement)

        # Actualizar saldo excluyendo créditos vencidos (igual que en el frontend)
        # El balance guardado debe coincidir con el balance mostrado al usuario
        wallet.balance = calculate_wallet_balance(wallet.id, include_expired=False)
        wallet.updated_at = datetime.utcnow()

        # Crear log de auditoría
        try:
            create_audit_log(
                admin_user_id=request.admin_user.id,
                action='wallet_manual_debit',
                entity='wallet',
                entity_id=wallet.id,
                details={
                    'user_id': str(user_id),
                    'amount': float(amount),
                    'reason': reason,
                    'internal_comment': internal_comment
                }
            )
        except Exception as audit_error:
            raise

        db.session.commit()

        return jsonify({
            'success': True,
            'data': {
                'wallet': wallet.to_dict(),
                'movement': movement.to_dict()
            }
        }), 200

    except IntegrityError as e:
        import traceback
        error_trace = traceback.format_exc()
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Error de integridad: ' + str(e),
            'traceback': error_trace
        }), 400
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': error_trace
        }), 500


@wallet_bp.route('/admin/wallet/customers/<uuid:user_id>/block', methods=['PUT'])
@admin_required
def toggle_block_wallet(user_id):
    """
    Bloquear o desbloquear billetera de cliente
    
    Body:
    {
        "is_blocked": true,
        "reason": "Abuso detectado"
    }
    """
    try:
        import traceback
        
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400

        is_blocked = data.get('is_blocked')
        reason = data.get('reason', '')

        if is_blocked is None:
            return jsonify({
                'success': False,
                'error': 'El campo is_blocked es requerido'
            }), 400

        user = User.query.get_or_404(user_id)
        
        wallet = get_or_create_wallet(user_id)

        wallet.is_blocked = bool(is_blocked)
        wallet.updated_at = datetime.utcnow()
        db.session.flush()

        # Crear log de auditoría
        action_type = 'wallet_block' if is_blocked else 'wallet_unblock'
        try:
            create_audit_log(
                admin_user_id=request.admin_user.id,
                action=action_type,
                entity='wallet',
                entity_id=wallet.id,
                details={
                    'user_id': str(user_id),
                    'is_blocked': is_blocked,
                    'reason': reason
                }
            )
        except Exception as audit_error:
            raise

        db.session.commit()

        return jsonify({
            'success': True,
            'data': wallet.to_dict(),
            'message': 'Billetera bloqueada' if is_blocked else 'Billetera desbloqueada'
        }), 200

    except IntegrityError as e:
        import traceback
        error_trace = traceback.format_exc()
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Error de integridad: ' + str(e),
            'traceback': error_trace
        }), 400
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': error_trace
        }), 500


# 5.3. CONTROL - Pantalla general de movimientos
@wallet_bp.route('/admin/wallet/movements', methods=['GET'])
@admin_required
def get_all_wallet_movements():
    """
    Obtener todos los movimientos de billetera con filtros
    
    Query parameters:
    - page: número de página (default: 1)
    - per_page: items por página (default: 50)
    - type: filtrar por tipo de movimiento
    - user_id: filtrar por cliente
    - start_date: fecha inicial (ISO format)
    - end_date: fecha final (ISO format)
    """
    try:
        import traceback
        
        # Paginación
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)

        # Filtros
        movement_type = request.args.get('type')
        user_id = request.args.get('user_id')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        # Query base con joins usando outerjoin para evitar problemas si no hay relación
        query = db.session.query(WalletMovement).outerjoin(Wallet, WalletMovement.wallet_id == Wallet.id).outerjoin(User, Wallet.user_id == User.id)

        # Filtro por tipo
        if movement_type:
            query = query.filter(WalletMovement.type == movement_type)

        # Filtro por usuario
        if user_id:
            try:
                user_uuid = uuid.UUID(user_id)
                query = query.filter(Wallet.user_id == user_uuid)
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'ID de usuario inválido'
                }), 400

        # Filtro por fecha
        if start_date:
            try:
                start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                query = query.filter(WalletMovement.created_at >= start)
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Formato de fecha inicial inválido (usar ISO format)'
                }), 400

        if end_date:
            try:
                end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                # Agregar un día para incluir todo el día final
                end = end + timedelta(days=1)
                query = query.filter(WalletMovement.created_at < end)
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Formato de fecha final inválido (usar ISO format)'
                }), 400

        # Ordenar por fecha descendente
        query = query.order_by(desc(WalletMovement.created_at))

        # Paginación
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        movements = pagination.items

        # Incluir información del usuario y billetera
        results = []
        for movement in movements:
            try:
                movement_dict = movement.to_dict(include_admin=True)
                
                # Cargar wallet y user de forma segura
                if movement.wallet_id:
                    wallet = Wallet.query.get(movement.wallet_id)
                    if wallet and wallet.user_id:
                        user = User.query.get(wallet.user_id)
                        if user:
                            movement_dict['user'] = {
                                'id': str(user.id),
                                'first_name': user.first_name,
                                'last_name': user.last_name,
                                'email': user.email
                            }
                
                results.append(movement_dict)
            except Exception as e:
                # Continuar con el siguiente movimiento aunque uno falle
                continue

        return jsonify({
            'success': True,
            'data': {
                'movements': results,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': pagination.total,
                    'pages': pagination.pages
                }
            }
        }), 200

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': error_trace
        }), 500


@wallet_bp.route('/admin/wallet/movements/export', methods=['GET'])
@admin_required
def export_wallet_movements():
    """
    Exportar movimientos de billetera a CSV (compatible con Excel)
    
    Query parameters (mismos filtros que get_all_wallet_movements):
    - type: filtrar por tipo de movimiento
    - user_id: filtrar por cliente
    - start_date: fecha inicial (ISO format)
    - end_date: fecha final (ISO format)
    """
    try:
        # Filtros (sin paginación para exportar todo)
        movement_type = request.args.get('type')
        user_id = request.args.get('user_id')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        # Query base con outerjoin para evitar errores si no hay relaciones
        query = db.session.query(WalletMovement).outerjoin(Wallet, WalletMovement.wallet_id == Wallet.id).outerjoin(User, Wallet.user_id == User.id)

        # Aplicar mismos filtros que get_all_wallet_movements
        if movement_type:
            query = query.filter(WalletMovement.type == movement_type)

        if user_id:
            try:
                user_uuid = uuid.UUID(user_id)
                query = query.filter(Wallet.user_id == user_uuid)
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'ID de usuario inválido'
                }), 400

        if start_date:
            try:
                start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                query = query.filter(WalletMovement.created_at >= start)
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Formato de fecha inicial inválido'
                }), 400

        if end_date:
            try:
                end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                end = end + timedelta(days=1)
                query = query.filter(WalletMovement.created_at < end)
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Formato de fecha final inválido'
                }), 400

        query = query.order_by(desc(WalletMovement.created_at))
        movements = query.all()

        # Crear CSV en memoria
        output = io.StringIO()
        writer = csv.writer(output)

        # Encabezados
        writer.writerow([
            'Fecha',
            'Cliente',
            'Email',
            'Tipo',
            'Monto',
            'Descripción',
            'Motivo',
            'Comentario Interno',
            'Admin',
            'Pedido ID'
        ])

        # Datos
        for movement in movements:
            user_name = ''
            user_email = ''
            try:
                if movement.wallet_id:
                    wallet = Wallet.query.get(movement.wallet_id)
                    if wallet and wallet.user_id:
                        user = User.query.get(wallet.user_id)
                        if user:
                            user_name = f"{user.first_name} {user.last_name}"
                            user_email = user.email
            except Exception:
                pass

            # Obtener email del admin, reason e internal_comment desde audit_logs si existe
            admin_email = ''
            reason = ''
            internal_comment = ''
            try:
                audit_log = AuditLog.query.filter_by(
                    entity='wallet',
                    entity_id=movement.wallet_id
                ).filter(
                    AuditLog.details['amount'].astext == str(movement.amount),
                    AuditLog.created_at <= movement.created_at
                ).order_by(AuditLog.created_at.desc()).first()
                
                if audit_log and audit_log.admin_user:
                    admin_email = audit_log.admin_user.email
                    if audit_log.details:
                        reason = audit_log.details.get('reason', '') or ''
                        internal_comment = audit_log.details.get('internal_comment', '') or ''
            except Exception as e:
                pass

            writer.writerow([
                movement.created_at.strftime('%Y-%m-%d %H:%M:%S') if movement.created_at else '',
                user_name,
                user_email,
                movement.type,
                float(movement.amount) if movement.amount else 0.0,
                movement.description or '',
                reason,
                internal_comment,
                admin_email,
                str(movement.order_id) if movement.order_id else ''
            ])

        # Crear respuesta
        output.seek(0)
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=wallet_movements_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            }
        )

        return response

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@wallet_bp.route('/admin/wallet/anomalies', methods=['GET'])
@admin_required
def detect_anomalies():
    """
    Detectar cosas raras:
    - Clientes con muchos ajustes manuales
    - Movimientos muy grandes
    
    Query parameters:
    - min_manual_adjustments: mínimo de ajustes manuales para considerar anómalo (default: 5)
    - min_amount: monto mínimo para considerar movimiento grande (default: 10000)
    """
    try:
        import traceback
        
        min_adjustments = request.args.get('min_manual_adjustments', 5, type=int)
        min_amount = request.args.get('min_amount', 10000, type=float)

        anomalies = {
            'many_manual_adjustments': [],
            'large_movements': []
        }

        # Clientes con muchos ajustes manuales
        manual_types = ['manual_credit', 'manual_debit']
        try:
            users_with_many_adjustments = db.session.query(
                User.id,
                User.first_name,
                User.last_name,
                User.email,
                func.count(WalletMovement.id).label('adjustment_count')
            ).outerjoin(Wallet, User.id == Wallet.user_id)\
             .outerjoin(WalletMovement, Wallet.id == WalletMovement.wallet_id)\
             .filter(WalletMovement.type.in_(manual_types))\
             .group_by(User.id, User.first_name, User.last_name, User.email)\
             .having(func.count(WalletMovement.id) >= min_adjustments)\
             .all()
        except Exception as e:
            users_with_many_adjustments = []

        for user_id, first_name, last_name, email, count in users_with_many_adjustments:
            anomalies['many_manual_adjustments'].append({
                'user_id': str(user_id),
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'adjustment_count': count
            })

        # Movimientos muy grandes
        try:
            large_movements = WalletMovement.query.filter(
                WalletMovement.amount >= min_amount
            ).order_by(desc(WalletMovement.amount)).limit(50).all()
        except Exception as e:
            large_movements = []

        for movement in large_movements:
            user_info = {}
            try:
                if movement.wallet_id:
                    wallet = Wallet.query.get(movement.wallet_id)
                    if wallet and wallet.user_id:
                        user = User.query.get(wallet.user_id)
                        if user:
                            user_info = {
                                'user_id': str(user.id),
                                'first_name': user.first_name,
                                'last_name': user.last_name,
                                'email': user.email
                            }
            except Exception:
                pass

            anomalies['large_movements'].append({
                'movement_id': str(movement.id),
                'user': user_info,
                'type': movement.type,
                'amount': float(movement.amount) if movement.amount else 0.0,
                'description': movement.description,
                'created_at': movement.created_at.isoformat() if movement.created_at else None
            })

        return jsonify({
            'success': True,
            'data': anomalies
        }), 200

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': error_trace
        }), 500


# ==================== ENDPOINTS PARA USUARIOS ====================

@wallet_bp.route('/wallet/balance', methods=['GET'])
@user_required
def get_user_wallet_balance():
    """
    Obtener el balance de la billetera del usuario autenticado
    El balance ya está calculado correctamente en la DB (excluyendo créditos vencidos)
    """
    try:
        user = request.user
        wallet = get_or_create_wallet(user.id)
        
        # Usar el balance guardado en la DB (ya excluye créditos vencidos)
        return jsonify({
            'success': True,
            'data': {
                'balance': float(wallet.balance) if wallet.balance else 0.0,
                'is_blocked': wallet.is_blocked
            }
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@wallet_bp.route('/wallet/movements', methods=['GET'])
@user_required
def get_user_wallet_movements():
    """
    Obtener historial de movimientos de billetera del usuario autenticado
    
    Query parameters:
    - page: número de página (default: 1)
    - per_page: items por página (default: 50)
    - type: filtrar por tipo de movimiento
    """
    try:
        user = request.user
        wallet = get_or_create_wallet(user.id)
        
        # Paginación
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)
        movement_type = request.args.get('type')
        
        # Query base
        query = WalletMovement.query.filter_by(wallet_id=wallet.id)
        
        # Filtro por tipo
        if movement_type:
            query = query.filter_by(type=movement_type)
        
        # Ordenar por fecha descendente
        query = query.order_by(desc(WalletMovement.created_at))
        
        # Paginación
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        movements = pagination.items
        
        return jsonify({
            'success': True,
            'data': {
                'movements': [movement.to_dict(include_admin=False) for movement in movements],
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
            'error': str(e)
        }), 500


@wallet_bp.route('/wallet/transfer', methods=['POST'])
@user_required
def transfer_wallet_balance():
    """
    Transferir saldo de billetera a otro usuario
    
    Body:
    - recipient_email: email del destinatario
    - amount: monto a transferir
    """
    try:
        user = request.user
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400
        
        recipient_email = data.get('recipient_email', '').strip().lower()
        amount = data.get('amount')
        
        # Validaciones
        if not recipient_email or '@' not in recipient_email:
            return jsonify({
                'success': False,
                'error': 'Email del destinatario inválido'
            }), 400
        
        if not amount or not isinstance(amount, (int, float)) or amount <= 0:
            return jsonify({
                'success': False,
                'error': 'Monto inválido. Debe ser mayor a 0'
            }), 400
        
        # No permitir transferirse a sí mismo
        if recipient_email == user.email.lower():
            return jsonify({
                'success': False,
                'error': 'No puedes transferir saldo a tu propia cuenta'
            }), 400
        
        # Buscar usuario destinatario
        recipient = User.query.filter(func.lower(User.email) == recipient_email).first()
        if not recipient:
            return jsonify({
                'success': False,
                'error': 'Usuario destinatario no encontrado'
            }), 404
        
        # Obtener billeteras
        sender_wallet = get_or_create_wallet(user.id)
        recipient_wallet = get_or_create_wallet(recipient.id)
        
        # Verificar que la billetera del remitente no esté bloqueada
        if sender_wallet.is_blocked:
            return jsonify({
                'success': False,
                'error': 'Tu billetera está bloqueada. No puedes realizar transferencias'
            }), 400
        
        # Verificar saldo suficiente
        sender_balance = float(sender_wallet.balance) if sender_wallet.balance else 0.0
        if sender_balance < amount:
            return jsonify({
                'success': False,
                'error': 'Saldo insuficiente'
            }), 400
        
        # Realizar transferencia
        try:
            # Debitar del remitente
            sender_movement = WalletMovement(
                wallet_id=sender_wallet.id,
                type='transfer_out',
                amount=-amount,
                description=f'Transferencia a {recipient_email}'
            )
            db.session.add(sender_movement)
            sender_wallet.balance = calculate_wallet_balance(sender_wallet.id, include_expired=False)
            
            # Acreditar al destinatario
            expires_at = calculate_expiration_date()
            recipient_movement = WalletMovement(
                wallet_id=recipient_wallet.id,
                type='transfer_in',
                amount=amount,
                description=f'Transferencia recibida de {user.email}',
                expires_at=expires_at
            )
            db.session.add(recipient_movement)
            recipient_wallet.balance = calculate_wallet_balance(recipient_wallet.id, include_expired=False)
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'data': {
                    'transfer_id': str(sender_movement.id),
                    'amount': amount,
                    'recipient_email': recipient_email,
                    'new_balance': float(sender_wallet.balance) if sender_wallet.balance else 0.0
                },
                'message': f'Transferencia de ${amount:.2f} realizada exitosamente'
            }), 200
            
        except IntegrityError as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'error': 'Error al procesar la transferencia'
            }), 500
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

