from flask import Blueprint, request, jsonify
from database import db
from models.product_review import ProductReview
from models.order import Order
from models.order_item import OrderItem
from models.product import Product
from routes.auth import user_required
from sqlalchemy import and_, func
from datetime import datetime, timedelta
from config import Config
from functools import wraps
import uuid

reviews_bp = Blueprint('reviews', __name__)

def api_key_required(f):
    """Decorador para proteger rutas que requieren API_KEY del .env"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = None
        
        # Buscar API key en header X-API-Key
        if 'X-API-Key' in request.headers:
            api_key = request.headers['X-API-Key']
        # O buscar en Authorization header
        elif 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                api_key = auth_header.split(' ')[1]
            else:
                api_key = auth_header
        
        if not api_key:
            return jsonify({
                'success': False,
                'error': 'API key requerida. Proporciona X-API-Key en el header o Authorization: Bearer <key>'
            }), 401
        
        if api_key != Config.API_KEY:
            return jsonify({
                'success': False,
                'error': 'API key inválida'
            }), 401
        
        return f(*args, **kwargs)
    
    return decorated_function

@reviews_bp.route('/reviews', methods=['POST'])
@user_required
def create_review():
    """
    Crear una reseña para un producto de una orden
    Solo se puede crear si el estado de la orden es 'finalizado'
    """
    try:
        user = request.user
        data = request.get_json()
        
        # Validar campos requeridos
        required_fields = ['order_id', 'order_item_id', 'product_id', 'rating']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Campo requerido faltante: {field}'
                }), 400
        
        # Validar rating (1-5)
        rating = data.get('rating')
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            return jsonify({
                'success': False,
                'error': 'El rating debe ser un número entre 1 y 5'
            }), 400
        
        # Obtener la orden
        try:
            order_id = uuid.UUID(data['order_id'])
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'order_id inválido'
            }), 400
        
        order = Order.query.filter_by(id=order_id, user_id=user.id).first()
        if not order:
            return jsonify({
                'success': False,
                'error': 'Orden no encontrada'
            }), 404
        
        # Verificar que el estado de la orden sea 'finalizado'
        if order.status != 'finalizado':
            return jsonify({
                'success': False,
                'error': f'Solo se pueden crear reseñas para órdenes con estado "finalizado". Estado actual: {order.status}'
            }), 400
        
        # Obtener el order_item
        try:
            order_item_id = uuid.UUID(data['order_item_id'])
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'order_item_id inválido'
            }), 400
        
        order_item = OrderItem.query.filter_by(
            id=order_item_id,
            order_id=order.id
        ).first()
        
        if not order_item:
            return jsonify({
                'success': False,
                'error': 'Item de orden no encontrado'
            }), 404
        
        # Verificar que el product_id coincida
        try:
            product_id = uuid.UUID(data['product_id'])
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'product_id inválido'
            }), 400
        
        if str(order_item.product_id) != str(product_id):
            return jsonify({
                'success': False,
                'error': 'El product_id no coincide con el item de la orden'
            }), 400
        
        # Verificar que no exista ya una reseña para este order_item
        existing_review = ProductReview.query.filter_by(
            order_item_id=order_item_id
        ).first()
        
        if existing_review:
            return jsonify({
                'success': False,
                'error': 'Ya existe una reseña para este item de orden'
            }), 400
        
        # Obtener product_variant_id si se proporciona (opcional)
        product_variant_id = None
        if 'product_variant_id' in data and data['product_variant_id']:
            try:
                product_variant_id = uuid.UUID(data['product_variant_id'])
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'product_variant_id inválido'
                }), 400
        
        # Crear la reseña
        review = ProductReview(
            user_id=user.id,
            order_id=order.id,
            order_item_id=order_item.id,
            product_id=product_id,
            product_variant_id=product_variant_id,
            rating=rating,
            title=data.get('title'),
            comment=data.get('comment'),
            status='published',
            is_verified_purchase=True
        )
        
        db.session.add(review)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': review.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Error al crear reseña: {str(e)}'
        }), 500


@reviews_bp.route('/reviews/order/<order_id>', methods=['GET'])
@user_required
def get_order_reviews(order_id):
    """
    Obtener todas las reseñas de una orden específica
    """
    try:
        user = request.user
        
        # Validar order_id
        try:
            order_uuid = uuid.UUID(order_id)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'order_id inválido'
            }), 400
        
        # Verificar que la orden pertenezca al usuario
        order = Order.query.filter_by(id=order_uuid, user_id=user.id).first()
        if not order:
            return jsonify({
                'success': False,
                'error': 'Orden no encontrada'
            }), 404
        
        # Obtener todas las reseñas de esta orden
        reviews = ProductReview.query.filter_by(order_id=order_uuid).all()
        
        return jsonify({
            'success': True,
            'data': {
                'reviews': [review.to_dict() for review in reviews],
                'order_id': str(order_uuid),
                'order_status': order.status
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error al obtener reseñas: {str(e)}'
        }), 500


@reviews_bp.route('/reviews/product/<product_id>', methods=['GET'])
def get_product_reviews(product_id):
    """
    Obtener todas las reseñas publicadas de un producto
    """
    try:
        # Validar product_id
        try:
            product_uuid = uuid.UUID(product_id)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'product_id inválido'
            }), 400
        
        # Verificar que el producto exista
        product = Product.query.get(product_uuid)
        if not product:
            return jsonify({
                'success': False,
                'error': 'Producto no encontrado'
            }), 404
        
        # Obtener solo reseñas publicadas
        reviews = ProductReview.query.filter_by(
            product_id=product_uuid,
            status='published'
        ).order_by(ProductReview.created_at.desc()).all()
        
        # Calcular rating promedio
        avg_rating = db.session.query(func.avg(ProductReview.rating)).filter_by(
            product_id=product_uuid,
            status='published'
        ).scalar()
        
        return jsonify({
            'success': True,
            'data': {
                'reviews': [review.to_dict() for review in reviews],
                'product_id': str(product_uuid),
                'total_reviews': len(reviews),
                'average_rating': float(avg_rating) if avg_rating else None
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error al obtener reseñas: {str(e)}'
        }), 500


@reviews_bp.route('/reviews/send-reminders', methods=['POST'])
@api_key_required
def send_review_reminders():
    """
    Endpoint para enviar emails de recordatorio a usuarios que tienen órdenes
    finalizadas sin reseñar y que pasaron más de 5 días desde la finalización.
    
    Este endpoint debería ser llamado por un cron job o tarea programada.
    """
    try:
        from utils.email_service import email_service
        from models.user import User
        from sqlalchemy import and_
        
        # Obtener todas las órdenes finalizadas
        finalizado_orders = Order.query.filter_by(status='finalizado').all()
        
        # Obtener todos los order_items de estas órdenes
        order_ids = [order.id for order in finalizado_orders]
        if not order_ids:
            return jsonify({
                'success': True,
                'message': 'No hay órdenes finalizadas',
                'emails_sent': 0
            }), 200
        
        order_items = OrderItem.query.filter(OrderItem.order_id.in_(order_ids)).all()
        
        # Obtener todas las reseñas existentes
        existing_reviews = ProductReview.query.filter(
            ProductReview.order_item_id.in_([item.id for item in order_items])
        ).all()
        
        reviewed_order_item_ids = {review.order_item_id for review in existing_reviews}
        
        # Filtrar order_items sin reseña
        unreviewed_items = [
            item for item in order_items 
            if item.id not in reviewed_order_item_ids
        ]
        
        # Agrupar por orden (un email por orden)
        orders_with_items = {}
        for item in unreviewed_items:
            order = next((o for o in finalizado_orders if o.id == item.order_id), None)
            if not order:
                continue
            
            # Verificar que hayan pasado más de 5 días desde la finalización
            # Usar finalized_at si está disponible, sino usar created_at como fallback
            finalization_date = order.finalized_at if order.finalized_at else order.created_at
            # Asegurar que ambos datetimes sean naive para la comparación
            if finalization_date.tzinfo is not None:
                finalization_date = finalization_date.replace(tzinfo=None)
            now = datetime.now()
            days_since_finalization = (now - finalization_date).days
            
            if days_since_finalization >= 5:
                if order.id not in orders_with_items:
                    orders_with_items[order.id] = {
                        'order': order,
                        'items': []
                    }
                orders_with_items[order.id]['items'].append(item)
        
        # Enviar emails (un email por orden)
        emails_sent = 0
        emails_failed = 0
        
        for order_id, data in orders_with_items.items():
            order = data['order']
            items = data['items']
            
            user = User.query.get(order.user_id)
            if not user or not user.email:
                continue
            
            # Construir URL de reseñas usando FRONTEND_URL del .env
            frontend_url = Config.FRONTEND_URL
            review_url = f"{frontend_url}/reviews/{order.id}"
            
            # Construir lista de productos únicos (sin duplicados)
            product_names_set = set()
            for item in items:
                product = Product.query.get(item.product_id)
                if product:
                    product_names_set.add(product.name)
            
            # Convertir a lista y limitar a 3 productos para mostrar
            product_names = list(product_names_set)[:3]
            products_text = ', '.join(product_names)
            if len(product_names_set) > 3:
                products_text += f" y {len(product_names_set) - 3} más"
            
            # Enviar email
            email_sent = email_service.send_custom_email(
                to=user.email,
                title="¿Cómo fue tu experiencia?",
                header_text="Tu opinión es importante",
                greeting=f"Hola {user.first_name},",
                main_content=f"""
                    <p>Hace más de 5 días que finalizó tu pedido y nos encantaría conocer tu opinión.</p>
                    <p>Productos: {products_text}</p>
                    <p>Tu feedback nos ayuda a mejorar y también ayuda a otros compradores a tomar mejores decisiones.</p>
                """,
                button_text="Dejar reseña",
                button_url=review_url,
                footer_note="Gracias por confiar en nosotros."
            )
            
            if email_sent:
                emails_sent += 1
            else:
                emails_failed += 1
        
        return jsonify({
            'success': True,
            'message': f'Proceso completado. {emails_sent} emails enviados, {emails_failed} fallidos',
            'emails_sent': emails_sent,
            'emails_failed': emails_failed,
            'orders_processed': len(orders_with_items)
        }), 200
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': f'Error al enviar recordatorios: {str(e)}'
        }), 500
