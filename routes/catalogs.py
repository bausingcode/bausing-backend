from flask import Blueprint, request, jsonify
from database import db
from models.catalog import Catalog, LocalityCatalog
from models.locality import Locality
from sqlalchemy.exc import IntegrityError
from routes.admin import admin_required

catalogs_bp = Blueprint('catalogs', __name__)

@catalogs_bp.route('', methods=['GET'])
def get_catalogs():
    """Obtener todos los catálogos con sus localidades"""
    # Limpiar cualquier transacción abortada antes de comenzar
    try:
        db.session.rollback()
    except:
        pass
    
    try:
        include_localities = request.args.get('include_localities', 'false').lower() == 'true'
        
        catalogs = Catalog.query.order_by(Catalog.name).all()
        
        return jsonify({
            'success': True,
            'data': [cat.to_dict(include_localities=include_localities) for cat in catalogs]
        }), 200
    except Exception as e:
        # Hacer rollback para limpiar cualquier transacción abortada
        try:
            db.session.rollback()
        except:
            pass
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@catalogs_bp.route('/<uuid:catalog_id>', methods=['GET'])
def get_catalog(catalog_id):
    """Obtener un catálogo por ID con sus localidades"""
    try:
        catalog = Catalog.query.get_or_404(catalog_id)
        
        return jsonify({
            'success': True,
            'data': catalog.to_dict(include_localities=True)
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

@catalogs_bp.route('', methods=['POST'])
@admin_required
def create_catalog():
    """Crear un nuevo catálogo"""
    try:
        data = request.get_json()
        
        if not data or not data.get('name'):
            return jsonify({
                'success': False,
                'error': 'El nombre es requerido'
            }), 400
        
        catalog = Catalog(
            name=data['name'],
            description=data.get('description')
        )
        
        db.session.add(catalog)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': catalog.to_dict()
        }), 201
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Error de integridad: Ya existe un catálogo con ese nombre'
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@catalogs_bp.route('/<uuid:catalog_id>', methods=['PUT'])
@admin_required
def update_catalog(catalog_id):
    """Actualizar un catálogo"""
    try:
        catalog = Catalog.query.get_or_404(catalog_id)
        data = request.get_json()
        
        if 'name' in data:
            catalog.name = data['name']
        if 'description' in data:
            catalog.description = data.get('description')
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': catalog.to_dict()
        }), 200
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Error de integridad: Ya existe un catálogo con ese nombre'
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@catalogs_bp.route('/<uuid:catalog_id>', methods=['DELETE'])
@admin_required
def delete_catalog(catalog_id):
    """Eliminar un catálogo"""
    try:
        catalog = Catalog.query.get_or_404(catalog_id)
        
        if catalog.product_prices:
            return jsonify({
                'success': False,
                'error': 'No se puede eliminar un catálogo que tiene precios asociados'
            }), 400
        
        db.session.delete(catalog)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Catálogo eliminado correctamente'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@catalogs_bp.route('/<uuid:catalog_id>/localities', methods=['GET'])
def get_catalog_localities(catalog_id):
    """Obtener todas las localidades de un catálogo"""
    try:
        catalog = Catalog.query.get_or_404(catalog_id)
        
        localities = [
            {
                'id': str(assoc.locality.id),
                'name': assoc.locality.name,
                'region': assoc.locality.region
            }
            for assoc in catalog.locality_associations
        ]
        
        return jsonify({
            'success': True,
            'data': localities
        }), 200
    except Exception as e:
        # Hacer rollback para limpiar cualquier transacción abortada
        try:
            db.session.rollback()
        except:
            pass
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@catalogs_bp.route('/<uuid:catalog_id>/localities', methods=['POST'])
@admin_required
def add_locality_to_catalog(catalog_id):
    """Agregar una localidad a un catálogo"""
    try:
        catalog = Catalog.query.get_or_404(catalog_id)
        data = request.get_json()
        
        if not data or not data.get('locality_id'):
            return jsonify({
                'success': False,
                'error': 'locality_id es requerido'
            }), 400
        
        locality_id = data['locality_id']
        locality = Locality.query.get_or_404(locality_id)
        
        # Verificar si ya existe la relación
        existing = LocalityCatalog.query.filter_by(
            catalog_id=catalog_id,
            locality_id=locality_id
        ).first()
        
        if existing:
            return jsonify({
                'success': False,
                'error': 'La localidad ya está asociada a este catálogo'
            }), 400
        
        association = LocalityCatalog(
            catalog_id=catalog_id,
            locality_id=locality_id
        )
        
        db.session.add(association)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': association.to_dict()
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

@catalogs_bp.route('/<uuid:catalog_id>/localities/<uuid:locality_id>', methods=['DELETE'])
@admin_required
def remove_locality_from_catalog(catalog_id, locality_id):
    """Remover una localidad de un catálogo"""
    try:
        association = LocalityCatalog.query.filter_by(
            catalog_id=catalog_id,
            locality_id=locality_id
        ).first_or_404()
        
        db.session.delete(association)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Localidad removida del catálogo correctamente'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@catalogs_bp.route('/<uuid:catalog_id>/localities', methods=['PUT'])
@admin_required
def update_catalog_localities(catalog_id):
    """Actualizar todas las localidades de un catálogo (reemplazar lista completa)"""
    try:
        catalog = Catalog.query.get_or_404(catalog_id)
        data = request.get_json()
        
        if not data or 'locality_ids' not in data:
            return jsonify({
                'success': False,
                'error': 'locality_ids es requerido (array de IDs de localidades)'
            }), 400
        
        locality_ids = data['locality_ids']
        
        # Eliminar todas las asociaciones existentes
        LocalityCatalog.query.filter_by(catalog_id=catalog_id).delete()
        
        # Crear nuevas asociaciones
        for locality_id in locality_ids:
            # Verificar que la localidad existe
            locality = Locality.query.get(locality_id)
            if not locality:
                continue
            
            association = LocalityCatalog(
                catalog_id=catalog_id,
                locality_id=locality_id
            )
            db.session.add(association)
        
        db.session.commit()
        
        # Retornar el catálogo actualizado
        catalog = Catalog.query.get_or_404(catalog_id)
        
        return jsonify({
            'success': True,
            'data': catalog.to_dict(include_localities=True)
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
