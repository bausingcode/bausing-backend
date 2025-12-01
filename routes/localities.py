from flask import Blueprint, request, jsonify
from database import db
from models.locality import Locality
from sqlalchemy.exc import IntegrityError

localities_bp = Blueprint('localities', __name__)

@localities_bp.route('', methods=['GET'])
def get_localities():
    """Obtener todas las localidades"""
    try:
        region = request.args.get('region')
        
        query = Locality.query
        if region:
            query = query.filter_by(region=region)
        
        localities = query.all()
        
        return jsonify({
            'success': True,
            'data': [loc.to_dict() for loc in localities]
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@localities_bp.route('/<uuid:locality_id>', methods=['GET'])
def get_locality(locality_id):
    """Obtener una localidad por ID"""
    try:
        locality = Locality.query.get_or_404(locality_id)
        
        return jsonify({
            'success': True,
            'data': locality.to_dict()
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

@localities_bp.route('', methods=['POST'])
def create_locality():
    """Crear una nueva localidad"""
    try:
        data = request.get_json()
        
        if not data or not data.get('name'):
            return jsonify({
                'success': False,
                'error': 'El nombre es requerido'
            }), 400
        
        locality = Locality(
            name=data['name'],
            region=data.get('region')
        )
        
        db.session.add(locality)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': locality.to_dict()
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

@localities_bp.route('/<uuid:locality_id>', methods=['PUT'])
def update_locality(locality_id):
    """Actualizar una localidad"""
    try:
        locality = Locality.query.get_or_404(locality_id)
        data = request.get_json()
        
        if 'name' in data:
            locality.name = data['name']
        if 'region' in data:
            locality.region = data.get('region')
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': locality.to_dict()
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

@localities_bp.route('/<uuid:locality_id>', methods=['DELETE'])
def delete_locality(locality_id):
    """Eliminar una localidad"""
    try:
        locality = Locality.query.get_or_404(locality_id)
        
        if locality.product_prices:
            return jsonify({
                'success': False,
                'error': 'No se puede eliminar una localidad que tiene precios asociados'
            }), 400
        
        db.session.delete(locality)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Localidad eliminada correctamente'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

