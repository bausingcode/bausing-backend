from flask import Blueprint, request, jsonify
from database import db
from models.product import ProductPrice
from sqlalchemy.exc import IntegrityError
from routes.admin import admin_required

prices_bp = Blueprint('prices', __name__)

@prices_bp.route('', methods=['GET'])
def get_prices():
    """Obtener todos los precios"""
    try:
        variant_id = request.args.get('variant_id')
        locality_id = request.args.get('locality_id')
        
        query = ProductPrice.query
        
        if variant_id:
            query = query.filter_by(product_variant_id=variant_id)
        if locality_id:
            query = query.filter_by(locality_id=locality_id)
        
        prices = query.all()
        
        return jsonify({
            'success': True,
            'data': [price.to_dict() for price in prices]
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@prices_bp.route('/<uuid:price_id>', methods=['GET'])
def get_price(price_id):
    """Obtener un precio por ID"""
    try:
        price = ProductPrice.query.get_or_404(price_id)
        
        return jsonify({
            'success': True,
            'data': price.to_dict()
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

@prices_bp.route('', methods=['POST'])
@admin_required
def create_price():
    """Crear un nuevo precio"""
    try:
        data = request.get_json()
        
        if not data or not data.get('product_variant_id') or not data.get('locality_id') or not data.get('price'):
            return jsonify({
                'success': False,
                'error': 'product_variant_id, locality_id y price son requeridos'
            }), 400
        
        # Verificar si ya existe un precio para esta combinación
        existing = ProductPrice.query.filter_by(
            product_variant_id=data['product_variant_id'],
            locality_id=data['locality_id']
        ).first()
        
        if existing:
            return jsonify({
                'success': False,
                'error': 'Ya existe un precio para esta variante y localidad'
            }), 400
        
        price = ProductPrice(
            product_variant_id=data['product_variant_id'],
            locality_id=data['locality_id'],
            price=data['price']
        )
        
        db.session.add(price)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': price.to_dict()
        }), 201
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Error de integridad: ' + str(e)
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@prices_bp.route('/<uuid:price_id>', methods=['PUT'])
@admin_required
def update_price(price_id):
    """Actualizar un precio"""
    try:
        price = ProductPrice.query.get_or_404(price_id)
        data = request.get_json()
        
        if 'price' in data:
            price.price = data['price']
        if 'locality_id' in data:
            price.locality_id = data['locality_id']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': price.to_dict()
        }), 200
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Error de integridad: ' + str(e)
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@prices_bp.route('/<uuid:price_id>', methods=['DELETE'])
@admin_required
def delete_price(price_id):
    """Eliminar un precio"""
    try:
        price = ProductPrice.query.get_or_404(price_id)
        
        db.session.delete(price)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Precio eliminado correctamente'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@prices_bp.route('/variant/<uuid:variant_id>/locality/<uuid:locality_id>', methods=['GET'])
def get_price_by_variant_locality(variant_id, locality_id):
    """Obtener precio por variante y localidad"""
    try:
        price = ProductPrice.query.filter_by(
            product_variant_id=variant_id,
            locality_id=locality_id
        ).first()
        
        if not price:
            return jsonify({
                'success': False,
                'error': 'Precio no encontrado'
            }), 404
        
        return jsonify({
            'success': True,
            'data': price.to_dict()
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

