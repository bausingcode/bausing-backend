from flask import Blueprint, request, jsonify
from database import db
from models.crm_delivery_zone import CrmDeliveryZone, CrmZoneLocality
from models.locality import Locality
from routes.admin import admin_required
from sqlalchemy.exc import IntegrityError
from decimal import Decimal

delivery_zones_bp = Blueprint('delivery_zones', __name__)


@delivery_zones_bp.route('', methods=['GET'])
@admin_required
def get_delivery_zones():
    """Obtener todas las zonas de entrega con sus localidades"""
    try:
        zones = CrmDeliveryZone.query.filter(
            CrmDeliveryZone.crm_deleted_at.is_(None)
        ).all()
        
        zones_data = []
        for zone in zones:
            zone_dict = zone.to_dict()
            # Obtener todas las localidades asociadas a esta zona
            zone_localities = CrmZoneLocality.query.filter_by(
                crm_zone_id=zone.crm_zone_id
            ).all()
            
            zone_dict['localities'] = [zl.to_dict() for zl in zone_localities]
            zones_data.append(zone_dict)
        
        return jsonify({
            'success': True,
            'data': zones_data
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@delivery_zones_bp.route('/zone-localities', methods=['GET'])
@admin_required
def get_zone_localities():
    """Obtener todas las asociaciones zona-localidad"""
    try:
        zone_localities = CrmZoneLocality.query.all()
        
        return jsonify({
            'success': True,
            'data': [zl.to_dict() for zl in zone_localities]
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@delivery_zones_bp.route('/zone-localities/<uuid:zone_locality_id>', methods=['GET'])
@admin_required
def get_zone_locality(zone_locality_id):
    """Obtener una asociación zona-localidad por ID"""
    try:
        zone_locality = CrmZoneLocality.query.get_or_404(zone_locality_id)
        
        return jsonify({
            'success': True,
            'data': zone_locality.to_dict()
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404


@delivery_zones_bp.route('/zone-localities/<uuid:zone_locality_id>', methods=['PUT'])
@admin_required
def update_zone_locality(zone_locality_id):
    """Actualizar una asociación zona-localidad (marcar como transporte tercerizado y establecer precio)"""
    try:
        zone_locality = CrmZoneLocality.query.get_or_404(zone_locality_id)
        data = request.get_json()
        
        if 'is_third_party_transport' in data:
            zone_locality.is_third_party_transport = bool(data['is_third_party_transport'])
        
        if 'shipping_price' in data:
            shipping_price = data['shipping_price']
            if shipping_price is not None:
                try:
                    zone_locality.shipping_price = Decimal(str(shipping_price))
                except (ValueError, TypeError):
                    return jsonify({
                        'success': False,
                        'error': 'El precio de envío debe ser un número válido'
                    }), 400
            else:
                zone_locality.shipping_price = None
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': zone_locality.to_dict()
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


@delivery_zones_bp.route('/zone-localities', methods=['POST'])
@admin_required
def create_zone_locality():
    """Crear una nueva asociación zona-localidad"""
    try:
        data = request.get_json()
        
        if not data or not data.get('crm_zone_id') or not data.get('locality_id'):
            return jsonify({
                'success': False,
                'error': 'crm_zone_id y locality_id son requeridos'
            }), 400
        
        # Verificar que la zona existe
        crm_zone = CrmDeliveryZone.query.filter_by(
            crm_zone_id=data['crm_zone_id']
        ).first()
        if not crm_zone:
            return jsonify({
                'success': False,
                'error': 'La zona de entrega no existe'
            }), 404
        
        # Verificar que la localidad existe
        locality = Locality.query.get(data['locality_id'])
        if not locality:
            return jsonify({
                'success': False,
                'error': 'La localidad no existe'
            }), 404
        
        # Verificar que no existe ya esta asociación
        existing = CrmZoneLocality.query.filter_by(
            crm_zone_id=data['crm_zone_id'],
            locality_id=data['locality_id']
        ).first()
        if existing:
            return jsonify({
                'success': False,
                'error': 'Esta asociación ya existe'
            }), 400
        
        zone_locality = CrmZoneLocality(
            crm_zone_id=data['crm_zone_id'],
            locality_id=data['locality_id'],
            is_third_party_transport=bool(data.get('is_third_party_transport', False)),
            shipping_price=Decimal(str(data['shipping_price'])) if data.get('shipping_price') else None
        )
        
        db.session.add(zone_locality)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': zone_locality.to_dict()
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


@delivery_zones_bp.route('/zone-localities/bulk-update', methods=['PUT'])
@admin_required
def bulk_update_zone_localities():
    """Actualizar múltiples asociaciones zona-localidad a la vez"""
    try:
        data = request.get_json()
        
        if not data or not isinstance(data, list):
            return jsonify({
                'success': False,
                'error': 'Se espera un array de objetos con id, is_third_party_transport y/o shipping_price'
            }), 400
        
        updated = []
        errors = []
        
        for item in data:
            if not item.get('id'):
                errors.append('Cada item debe tener un id')
                continue
            
            try:
                zone_locality = CrmZoneLocality.query.get(item['id'])
                if not zone_locality:
                    errors.append(f'No se encontró la asociación con id {item["id"]}')
                    continue
                
                if 'is_third_party_transport' in item:
                    zone_locality.is_third_party_transport = bool(item['is_third_party_transport'])
                
                if 'shipping_price' in item:
                    shipping_price = item['shipping_price']
                    if shipping_price is not None:
                        try:
                            zone_locality.shipping_price = Decimal(str(shipping_price))
                        except (ValueError, TypeError):
                            errors.append(f'Precio de envío inválido para id {item["id"]}')
                            continue
                    else:
                        zone_locality.shipping_price = None
                
                updated.append(zone_locality.to_dict())
            except Exception as e:
                errors.append(f'Error actualizando id {item.get("id")}: {str(e)}')
        
        if errors and not updated:
            return jsonify({
                'success': False,
                'error': 'Errores al actualizar: ' + '; '.join(errors)
            }), 400
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': updated,
            'errors': errors if errors else None
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
