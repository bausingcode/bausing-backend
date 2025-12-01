from flask import Blueprint, request, jsonify
from database import db
from models.product import ProductVariant
from sqlalchemy.exc import IntegrityError

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
def create_variant():
    """Crear una nueva variante de producto"""
    try:
        data = request.get_json()
        
        if not data or not data.get('product_id') or not data.get('variant_name'):
            return jsonify({
                'success': False,
                'error': 'product_id y variant_name son requeridos'
            }), 400
        
        # Construir variant_name automáticamente si se proporcionan atributos
        variant_name = data.get('variant_name')
        attributes = data.get('attributes', {})
        
        # Si no hay variant_name pero hay atributos, generar uno
        if not variant_name and attributes:
            parts = []
            if attributes.get('size'):
                parts.append(attributes['size'])
            if attributes.get('combo'):
                parts.append(attributes['combo'])
            if attributes.get('model'):
                parts.append(attributes['model'])
            if attributes.get('color'):
                parts.append(attributes['color'])
            if attributes.get('dimensions'):
                parts.append(attributes['dimensions'])
            variant_name = ' - '.join(parts) if parts else 'Variante'
        
        variant = ProductVariant(
            product_id=data['product_id'],
            variant_name=variant_name or data.get('variant_name', 'Variante'),
            stock=data.get('stock', 0),
            attributes=attributes if attributes else None
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
def update_variant(variant_id):
    """Actualizar una variante de producto"""
    try:
        variant = ProductVariant.query.get_or_404(variant_id)
        data = request.get_json()
        
        if 'attributes' in data:
            variant.attributes = data.get('attributes', {})
            # Regenerar variant_name si se actualizaron atributos
            if variant.attributes:
                parts = []
                if variant.attributes.get('size'):
                    parts.append(variant.attributes['size'])
                if variant.attributes.get('combo'):
                    parts.append(variant.attributes['combo'])
                if variant.attributes.get('model'):
                    parts.append(variant.attributes['model'])
                if variant.attributes.get('color'):
                    parts.append(variant.attributes['color'])
                if variant.attributes.get('dimensions'):
                    parts.append(variant.attributes['dimensions'])
                if parts:
                    variant.variant_name = ' - '.join(parts)
        
        if 'variant_name' in data:
            variant.variant_name = data['variant_name']
        if 'stock' in data:
            variant.stock = data.get('stock', 0)
        
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

