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
