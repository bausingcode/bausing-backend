from flask import Blueprint, request, jsonify
from database import db
from models.category import Category, CategoryOption
from sqlalchemy.exc import IntegrityError
from routes.admin import admin_required

categories_bp = Blueprint('categories', __name__)

@categories_bp.route('', methods=['GET'])
def get_categories():
    """Obtener todas las categorías (opcionalmente filtradas por parent_id)"""
    try:
        parent_id = request.args.get('parent_id')
        include_children = request.args.get('include_children', 'false').lower() == 'true'
        include_options = request.args.get('include_options', 'false').lower() == 'true'
        
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
                cat_dict = cat.to_dict(include_options=include_options)
                if cat.children:
                    cat_dict['subcategories'] = [child.to_dict(include_options=include_options) for child in cat.children]
                category_dicts.append(cat_dict)
            return jsonify({
                'success': True,
                'data': category_dicts
            }), 200
        else:
            return jsonify({
                'success': True,
                'data': [cat.to_dict(include_options=include_options) for cat in categories]
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
        include_options = request.args.get('include_options', 'false').lower() == 'true'
        return jsonify({
            'success': True,
            'data': category.to_dict(include_options=include_options)
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

@categories_bp.route('', methods=['POST'])
@admin_required
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
@admin_required
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
@admin_required
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

# Category Options endpoints

@categories_bp.route('/<uuid:category_id>/options', methods=['GET'])
def get_category_options(category_id):
    """Obtener todas las opciones de una categoría"""
    try:
        Category.query.get_or_404(category_id)  # Verificar que la categoría existe
        options = CategoryOption.query.filter_by(category_id=category_id).order_by(CategoryOption.position).all()
        
        return jsonify({
            'success': True,
            'data': [option.to_dict() for option in options]
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@categories_bp.route('/<uuid:category_id>/options', methods=['POST'])
@admin_required
def create_category_option(category_id):
    """Crear una nueva opción para una categoría"""
    try:
        Category.query.get_or_404(category_id)  # Verificar que la categoría existe
        data = request.get_json()
        
        if not data or not data.get('value'):
            return jsonify({
                'success': False,
                'error': 'El valor es requerido'
            }), 400
        
        option = CategoryOption(
            category_id=category_id,
            value=data['value'],
            position=data.get('position', 0)
        )
        
        db.session.add(option)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': option.to_dict()
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

@categories_bp.route('/<uuid:category_id>/options/<uuid:option_id>', methods=['GET'])
def get_category_option(category_id, option_id):
    """Obtener una opción específica de una categoría"""
    try:
        Category.query.get_or_404(category_id)  # Verificar que la categoría existe
        option = CategoryOption.query.filter_by(id=option_id, category_id=category_id).first_or_404()
        
        return jsonify({
            'success': True,
            'data': option.to_dict()
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

@categories_bp.route('/<uuid:category_id>/options/<uuid:option_id>', methods=['PUT'])
@admin_required
def update_category_option(category_id, option_id):
    """Actualizar una opción de categoría"""
    try:
        Category.query.get_or_404(category_id)  # Verificar que la categoría existe
        option = CategoryOption.query.filter_by(id=option_id, category_id=category_id).first_or_404()
        data = request.get_json()
        
        if 'value' in data:
            option.value = data['value']
        if 'position' in data:
            option.position = data['position']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': option.to_dict()
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

@categories_bp.route('/<uuid:category_id>/options/<uuid:option_id>', methods=['DELETE'])
@admin_required
def delete_category_option(category_id, option_id):
    """Eliminar una opción de categoría"""
    try:
        Category.query.get_or_404(category_id)  # Verificar que la categoría existe
        option = CategoryOption.query.filter_by(id=option_id, category_id=category_id).first_or_404()
        
        # Verificar si hay productos usando esta opción
        from models.product import Product
        products_with_option = Product.query.filter_by(category_option_id=option_id).first()
        if products_with_option:
            return jsonify({
                'success': False,
                'error': 'No se puede eliminar una opción que está siendo usada por productos'
            }), 400
        
        db.session.delete(option)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Opción eliminada correctamente'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

