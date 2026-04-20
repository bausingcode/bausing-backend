from flask import Blueprint, request, jsonify
from sqlalchemy import delete
from database import db
from models.category import Category, CategoryOption
from models.product import ProductSubcategory
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from routes.admin import admin_required
import uuid as uuid_lib

categories_bp = Blueprint('categories', __name__)


def _resolve_parent_category_id(raw_parent_id):
    """
    Normaliza parent_id (string/UUID) para categorías hijas.
    Solo se permiten padres que sean categorías principales (sin parent_id).
    Retorna (uuid_obj | None, error_message | None).
    """
    if raw_parent_id is None or raw_parent_id == '':
        return None, None
    try:
        pid = (
            raw_parent_id
            if isinstance(raw_parent_id, uuid_lib.UUID)
            else uuid_lib.UUID(str(raw_parent_id).strip())
        )
    except (ValueError, TypeError, AttributeError):
        return None, 'parent_id no es un UUID válido'
    parent = db.session.get(Category, pid)
    if not parent:
        return None, 'La categoría padre no existe'
    if parent.parent_id is not None:
        return None, 'Solo se pueden crear subcategorías bajo una categoría principal'
    return pid, None


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

        if include_children:
            query = query.options(
                joinedload(Category.options),
                joinedload(Category.children).joinedload(Category.options),
            )
        elif include_options:
            query = query.options(joinedload(Category.options))
        
        # Ordenar por el campo 'order' y luego por nombre como fallback
        categories = query.order_by(Category.order, Category.name).all()
        
        # Si se solicita incluir hijos, construir el árbol
        if include_children:
            category_dicts = []
            for cat in categories:
                cat_dict = cat.to_dict(include_options=include_options)
                if cat.children:
                    cat_dict['subcategories'] = [child.to_dict(include_options=include_options) for child in cat.children]
                category_dicts.append(cat_dict)
            resp = jsonify({
                'success': True,
                'data': category_dicts
            })
            resp.headers['Cache-Control'] = 'public, max-age=60'
            return resp, 200
        else:
            resp = jsonify({
                'success': True,
                'data': [cat.to_dict(include_options=include_options) for cat in categories]
            })
            resp.headers['Cache-Control'] = 'public, max-age=60'
            return resp, 200
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

        parent_uuid, parent_err = _resolve_parent_category_id(data.get('parent_id'))
        if parent_err:
            return jsonify({'success': False, 'error': parent_err}), 400
        
        raw_icon = data.get('navbar_icon_key')
        icon_key = (raw_icon.strip() or None) if isinstance(raw_icon, str) else None

        category = Category(
            name=data['name'],
            description=data.get('description'),
            parent_id=parent_uuid,
            navbar_image_url=data.get('navbar_image_url'),
            navbar_icon_key=icon_key,
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
            raw = data['parent_id']
            if raw is None or raw == '':
                category.parent_id = None
            else:
                if str(raw) == str(category_id):
                    return jsonify({
                        'success': False,
                        'error': 'Una categoría no puede ser padre de sí misma',
                    }), 400
                parent_uuid, parent_err = _resolve_parent_category_id(raw)
                if parent_err:
                    return jsonify({'success': False, 'error': parent_err}), 400
                category.parent_id = parent_uuid
        if 'navbar_image_url' in data:
            category.navbar_image_url = data.get('navbar_image_url') or None
        if 'order' in data:
            raw_order = data.get('order')
            if raw_order is None:
                category.order = 0
            else:
                try:
                    category.order = int(raw_order)
                except (TypeError, ValueError):
                    return jsonify({'success': False, 'error': 'order inválido'}), 400
        if 'navbar_icon_key' in data:
            raw_icon = data.get('navbar_icon_key')
            category.navbar_icon_key = (raw_icon.strip() or None) if isinstance(raw_icon, str) else None

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

@categories_bp.route('/<string:category_id>', methods=['DELETE'])
@admin_required
def delete_category(category_id):
    """Eliminar una categoría"""
    try:
        try:
            cid = uuid_lib.UUID(category_id.strip())
        except (ValueError, AttributeError):
            return jsonify({
                'success': False,
                'error': 'ID de categoría inválido'
            }), 400

        category = db.session.get(Category, cid)
        if not category:
            return jsonify({
                'success': False,
                'error': 'Categoría no encontrada'
            }), 404

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

        # Evitar que el ORM emita UPDATE con FKs NULL (passive_deletes no cubre todos los casos).
        db.session.execute(delete(ProductSubcategory).where(ProductSubcategory.subcategory_id == cid))
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
        
        raw_opt_icon = data.get('navbar_icon_key')
        opt_icon = (raw_opt_icon.strip() or None) if isinstance(raw_opt_icon, str) else None

        option = CategoryOption(
            category_id=category_id,
            value=data['value'],
            position=data.get('position', 0),
            navbar_icon_key=opt_icon,
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
        if 'navbar_icon_key' in data:
            raw_opt_icon = data.get('navbar_icon_key')
            option.navbar_icon_key = (raw_opt_icon.strip() or None) if isinstance(raw_opt_icon, str) else None

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

