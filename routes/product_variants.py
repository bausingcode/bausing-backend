from flask import Blueprint, request, jsonify
from database import db
from models.product import ProductVariant
from sqlalchemy.exc import IntegrityError
from routes.admin import admin_required

variants_bp = Blueprint('variants', __name__)

@variants_bp.route('', methods=['GET'])
def get_variants():
    """Obtener todas las variantes de productos"""
    try:
        product_id = request.args.get('product_id')
        include_prices = request.args.get('include_prices', 'false').lower() == 'true'
        
        query = ProductVariant.query
        
        if product_id:
            query = query.filter_by(product_id=product_id)
        
        variants = query.all()
        
        return jsonify({
            'success': True,
            'data': [variant.to_dict(include_prices=include_prices) for variant in variants]
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@variants_bp.route('/<uuid:variant_id>', methods=['GET'])
def get_variant(variant_id):
    """Obtener una variante por ID"""
    try:
        include_prices = request.args.get('include_prices', 'true').lower() == 'true'
        variant = ProductVariant.query.get_or_404(variant_id)
        
        return jsonify({
            'success': True,
            'data': variant.to_dict(include_prices=include_prices)
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

@variants_bp.route('', methods=['POST'])
@admin_required
def create_variant():
    """Crear una nueva variante de producto"""
    try:
        data = request.get_json()
        
        if not data or not data.get('product_id'):
            return jsonify({
                'success': False,
                'error': 'product_id es requerido'
            }), 400
        
        variant = ProductVariant(
            product_id=data['product_id'],
            sku=data.get('sku'),
            stock=data.get('stock', 0),
            price=data.get('price')
        )
        
        db.session.add(variant)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': variant.to_dict()
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

@variants_bp.route('/<uuid:variant_id>', methods=['PUT'])
@admin_required
def update_variant(variant_id):
    """Actualizar una variante de producto"""
    try:
        variant = ProductVariant.query.get_or_404(variant_id)
        data = request.get_json()
        
        if 'sku' in data:
            variant.sku = data.get('sku')
        if 'stock' in data:
            variant.stock = data.get('stock', 0)
        if 'price' in data:
            variant.price = data.get('price')
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': variant.to_dict()
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

@variants_bp.route('/<uuid:variant_id>', methods=['DELETE'])
@admin_required
def delete_variant(variant_id):
    """Eliminar una variante de producto"""
    try:
        variant = ProductVariant.query.get_or_404(variant_id)
        
        db.session.delete(variant)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Variante eliminada correctamente'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@variants_bp.route('/<uuid:variant_id>/stock', methods=['PATCH'])
@admin_required
def update_stock(variant_id):
    """Actualizar el stock de una variante"""
    try:
        variant = ProductVariant.query.get_or_404(variant_id)
        data = request.get_json()
        
        if 'stock' not in data:
            return jsonify({
                'success': False,
                'error': 'El stock es requerido'
            }), 400
        
        variant.stock = data['stock']
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': variant.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

