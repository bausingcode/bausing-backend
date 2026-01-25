from flask import Blueprint, request, jsonify
from database import db
from models.order import Order
from models.address import Address
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from routes.auth import user_required
import uuid

orders_bp = Blueprint('orders', __name__)

@orders_bp.route('/orders', methods=['GET'])
@user_required
def get_user_orders():
    """
    Obtener todas las órdenes del usuario autenticado
    
    Query parameters:
    - page: número de página (default: 1)
    - per_page: items por página (default: 50, max: 100)
    - status: filtrar por estado (pending, in_transit, pending_delivery, delivered, cancelled)
    """
    try:
        user = request.user
        
        # Paginación
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)
        status_filter = request.args.get('status')
        
        # Query base
        query = Order.query.filter_by(user_id=user.id)
        
        # Filtro por estado
        if status_filter:
            query = query.filter_by(status=status_filter)
        
        # Ordenar por fecha descendente (más recientes primero)
        query = query.order_by(desc(Order.created_at))
        
        # Paginación
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        orders = pagination.items
        
        # Convertir órdenes a formato esperado por el frontend
        orders_data = []
        for order in orders:
            order_dict = order_to_dict(order)
            orders_data.append(order_dict)
        
        return jsonify({
            'success': True,
            'data': {
                'orders': orders_data,
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
            'error': f'Error al obtener órdenes: {str(e)}'
        }), 500


@orders_bp.route('/orders/<order_id>', methods=['GET'])
@user_required
def get_user_order(order_id):
    """
    Obtener una orden específica del usuario autenticado
    """
    try:
        user = request.user
        
        # Validar que el order_id sea un UUID válido
        try:
            order_uuid = uuid.UUID(order_id)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'ID de orden inválido'
            }), 400
        
        # Buscar la orden
        order = Order.query.filter_by(id=order_uuid, user_id=user.id).first()
        
        if not order:
            return jsonify({
                'success': False,
                'error': 'Orden no encontrada'
            }), 404
        
        # Convertir orden a formato esperado por el frontend
        order_dict = order_to_dict(order)
        
        return jsonify({
            'success': True,
            'data': order_dict
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error al obtener orden: {str(e)}'
        }), 500


def order_to_dict(order):
    """
    Convierte una orden del modelo a el formato esperado por el frontend
    """
    from sqlalchemy import text
    
    # Obtener la dirección de envío (si existe)
    shipping_address = None
    # Por ahora, obtenemos la primera dirección del usuario como dirección de envío
    # En el futuro, esto debería venir de una tabla order_addresses o similar
    address = Address.query.filter_by(user_id=order.user_id).first()
    if address:
        shipping_address = address.to_dict()
    
    # Obtener items de la orden
    # Por ahora, como no hay tabla order_items, retornamos un array vacío
    # En el futuro, esto debería venir de una tabla order_items
    items = []
    
    # Determinar payment_status basado en el status de la orden
    payment_status = "pending"
    if order.status in ["in_transit", "pending_delivery", "delivered"]:
        payment_status = "paid"
    elif order.status == "cancelled":
        payment_status = "failed"
    
    # Determinar pay_on_delivery
    pay_on_delivery = order.payment_method == "cash" and payment_status == "pending"
    
    # Obtener receipt_number desde crm_orders usando crm_order_id
    order_number = None
    if hasattr(order, 'crm_order_id') and order.crm_order_id:
        try:
            receipt_query = text("""
                SELECT receipt_number 
                FROM crm_orders 
                WHERE crm_order_id = :crm_order_id
            """)
            receipt_result = db.session.execute(receipt_query, {
                'crm_order_id': order.crm_order_id
            })
            receipt_row = receipt_result.fetchone()
            if receipt_row and receipt_row[0]:
                order_number = receipt_row[0]
        except Exception:
            pass
    
    # Si no se encontró receipt_number, usar valor por defecto
    if not order_number:
        order_number = f"ORD-{order.created_at.strftime('%Y')}-{str(order.id)[:8].upper()}"
    
    return {
        'id': str(order.id),
        'user_id': str(order.user_id),
        'order_number': order_number,
        'status': order.status,
        'payment_method': order.payment_method or 'card',
        'payment_status': payment_status,
        'pay_on_delivery': pay_on_delivery,
        'total_amount': float(order.total) if order.total else 0.0,
        'shipping_address': shipping_address,
        'items': items,
        'tracking_number': None,  # Por ahora None, se puede agregar después
        'tracking_url': None,  # Por ahora None, se puede agregar después
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'updated_at': order.created_at.isoformat() if order.created_at else None  # Por ahora usamos created_at
    }
