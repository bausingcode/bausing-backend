from flask import Blueprint, request, jsonify
from database import db
from models.category import Category
from sqlalchemy.exc import IntegrityError

categories_bp = Blueprint('categories', __name__)

@categories_bp.route('', methods=['GET'])
def get_categories():
    """Obtener todas las categorías (opcionalmente filtradas por parent_id)"""
    try:
        parent_id = request.args.get('parent_id')
        include_children = request.args.get('include_children', 'false').lower() == 'true'
        
        query = Category.query
        if parent_id:
            query = query.filter_by(parent_id=parent_id)
        elif parent_id == '':
            query = query.filter_by(parent_id=None)
        
        categories = query.all()
        
        # Si se solicita incluir hijos, construir el árbol
        if include_children:
            category_dicts = []
            for cat in categories:
                cat_dict = cat.to_dict()
                if cat.children:
                    cat_dict['subcategories'] = [child.to_dict() for child in cat.children]
                category_dicts.append(cat_dict)
            return jsonify({
                'success': True,
                'data': category_dicts
            }), 200
        else:
            return jsonify({
                'success': True,
                'data': [cat.to_dict() for cat in categories]
            }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@categories_bp.route('/<uuid:category_id>', methods=['GET'])
def get_category(category_id):
    """Obtener una categoría por ID"""
    try:
        category = Category.query.get_or_404(category_id)
        return jsonify({
            'success': True,
            'data': category.to_dict()
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

@categories_bp.route('', methods=['POST'])
def create_category():
    """Crear una nueva categoría"""
    try:
        data = request.get_json()
        
        if not data or not data.get('name'):
            return jsonify({
                'success': False,
                'error': 'El nombre es requerido'
            }), 400
        
        category = Category(
            name=data['name'],
            description=data.get('description'),
            parent_id=data.get('parent_id')
        )
        
        db.session.add(category)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': category.to_dict()
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

@categories_bp.route('/<uuid:category_id>', methods=['PUT'])
def update_category(category_id):
    """Actualizar una categoría"""
    try:
        category = Category.query.get_or_404(category_id)
        data = request.get_json()
        
        if 'name' in data:
            category.name = data['name']
        if 'description' in data:
            category.description = data.get('description')
        if 'parent_id' in data:
            # Evitar referencia circular
            if data['parent_id'] and data['parent_id'] != str(category_id):
                category.parent_id = data['parent_id']
            elif data['parent_id'] is None:
                category.parent_id = None
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': category.to_dict()
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

@categories_bp.route('/<uuid:category_id>', methods=['DELETE'])
def delete_category(category_id):
    """Eliminar una categoría"""
    try:
        category = Category.query.get_or_404(category_id)
        
        # Verificar si tiene productos o categorías hijas
        if category.products:
            return jsonify({
                'success': False,
                'error': 'No se puede eliminar una categoría que tiene productos asociados'
            }), 400
        
        if category.children:
            return jsonify({
                'success': False,
                'error': 'No se puede eliminar una categoría que tiene subcategorías'
            }), 400
        
        db.session.delete(category)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Categoría eliminada correctamente'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@categories_bp.route('/<uuid:category_id>/products', methods=['GET'])
def get_category_products(category_id):
    """Obtener todos los productos de una categoría"""
    try:
        category = Category.query.get_or_404(category_id)
        products = category.products
        
        return jsonify({
            'success': True,
            'data': [product.to_dict() for product in products]
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

