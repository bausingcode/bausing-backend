from flask import Blueprint, request, jsonify
from database import db
from models.event import Event
from datetime import datetime
from routes.admin import admin_required

events_bp = Blueprint('events', __name__)

@events_bp.route('/public/active', methods=['GET'])
def get_active_event():
    """Obtener el evento activo (público)"""
    try:
        event = Event.query.filter_by(is_active=True).first()
        
        if not event:
            return jsonify({
                'success': True,
                'data': None
            }), 200
        
        return jsonify({
            'success': True,
            'data': event.to_dict()
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@events_bp.route('/admin/events', methods=['GET'])
@admin_required
def get_events():
    """Obtener todos los eventos (admin)"""
    try:
        events = Event.query.order_by(Event.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'data': [event.to_dict() for event in events]
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@events_bp.route('/admin/events/<uuid:event_id>', methods=['GET'])
@admin_required
def get_event(event_id):
    """Obtener un evento por ID (admin)"""
    try:
        event = Event.query.get_or_404(event_id)
        
        return jsonify({
            'success': True,
            'data': event.to_dict()
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

@events_bp.route('/admin/events', methods=['POST'])
@admin_required
def create_event():
    """Crear un nuevo evento (admin)"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400
        
        # Validaciones
        if not data.get('text'):
            return jsonify({
                'success': False,
                'error': 'El texto es requerido'
            }), 400
        
        if data.get('display_type') not in ['fixed', 'countdown']:
            return jsonify({
                'success': False,
                'error': 'display_type debe ser "fixed" o "countdown"'
            }), 400
        
        # Si es countdown, validar countdown_end_date
        countdown_end_date = None
        if data.get('display_type') == 'countdown':
            if not data.get('countdown_end_date'):
                return jsonify({
                    'success': False,
                    'error': 'countdown_end_date es requerido cuando display_type es "countdown"'
                }), 400
            try:
                countdown_end_date = datetime.fromisoformat(data['countdown_end_date'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                return jsonify({
                    'success': False,
                    'error': 'countdown_end_date debe ser una fecha válida en formato ISO'
                }), 400
        
        # Si se activa este evento, desactivar los demás
        if data.get('is_active', False):
            Event.query.update({Event.is_active: False})
        
        event = Event(
            text=data['text'],
            background_color=data.get('background_color', '#111827'),
            text_color=data.get('text_color', '#FFFFFF'),
            is_active=data.get('is_active', False),
            display_type=data.get('display_type', 'fixed'),
            countdown_end_date=countdown_end_date
        )
        
        db.session.add(event)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': event.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@events_bp.route('/admin/events/<uuid:event_id>', methods=['PUT'])
@admin_required
def update_event(event_id):
    """Actualizar un evento (admin)"""
    try:
        event = Event.query.get_or_404(event_id)
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400
        
        # Validaciones
        if 'text' in data and not data['text']:
            return jsonify({
                'success': False,
                'error': 'El texto no puede estar vacío'
            }), 400
        
        if 'display_type' in data and data['display_type'] not in ['fixed', 'countdown']:
            return jsonify({
                'success': False,
                'error': 'display_type debe ser "fixed" o "countdown"'
            }), 400
        
        # Actualizar campos
        if 'text' in data:
            event.text = data['text']
        if 'background_color' in data:
            event.background_color = data['background_color']
        if 'text_color' in data:
            event.text_color = data['text_color']
        if 'display_type' in data:
            event.display_type = data['display_type']
        
        # Manejar countdown_end_date
        if 'countdown_end_date' in data:
            if data['countdown_end_date'] is None:
                event.countdown_end_date = None
            else:
                try:
                    event.countdown_end_date = datetime.fromisoformat(data['countdown_end_date'].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    return jsonify({
                        'success': False,
                        'error': 'countdown_end_date debe ser una fecha válida en formato ISO o null'
                    }), 400
        
        # Si se activa este evento, desactivar los demás
        if 'is_active' in data:
            if data['is_active']:
                Event.query.filter(Event.id != event_id).update({Event.is_active: False})
            event.is_active = data['is_active']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': event.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@events_bp.route('/admin/events/<uuid:event_id>', methods=['DELETE'])
@admin_required
def delete_event(event_id):
    """Eliminar un evento (admin)"""
    try:
        event = Event.query.get_or_404(event_id)
        
        db.session.delete(event)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Evento eliminado correctamente'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@events_bp.route('/admin/events/<uuid:event_id>/toggle', methods=['PUT'])
@admin_required
def toggle_event(event_id):
    """Activar/desactivar un evento (admin)"""
    try:
        event = Event.query.get_or_404(event_id)
        
        # Si se va a activar, desactivar los demás
        if not event.is_active:
            Event.query.update({Event.is_active: False})
        
        event.is_active = not event.is_active
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': event.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
