from flask import Blueprint, request, jsonify
from database import db
from models.settings import SystemSettings, MessageTemplate, NotificationSetting, SecuritySetting
from routes.admin import admin_required
from datetime import datetime
import json

settings_bp = Blueprint('settings', __name__)
public_settings_bp = Blueprint('public_settings', __name__)

@public_settings_bp.route('/settings/public/phone', methods=['GET'])
def get_public_phone():
    """
    Obtener número de teléfono público (sin autenticación)
    """
    try:
        phone_setting = SystemSettings.query.filter_by(key='general.phone').first()
        
        if phone_setting:
            return jsonify({
                'success': True,
                'phone': phone_setting.value
            }), 200
        else:
            return jsonify({
                'success': True,
                'phone': None
            }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/settings', methods=['GET'])
@admin_required
def get_settings():
    """
    Obtener toda la configuración del sistema
    """
    try:
        # Obtener configuración de billetera
        wallet_settings = SystemSettings.query.filter_by(category='wallet').all()
        wallet_config = {}
        for setting in wallet_settings:
            key = setting.key.replace('wallet.', '')
            if setting.value_type == 'number':
                wallet_config[key] = float(setting.value)
            elif setting.value_type == 'boolean':
                wallet_config[key] = setting.value.lower() in ('true', '1', 'yes', 'on')
            else:
                wallet_config[key] = setting.value

        # Obtener mensajes automáticos
        message_templates = MessageTemplate.query.all()
        messages = {}
        for template in message_templates:
            messages[template.type] = {
                'subject': template.subject,
                'body': template.body,
                'variables': template.variables or []
            }

        # Obtener configuración de notificaciones del usuario actual
        notification_settings = NotificationSetting.query.filter_by(
            admin_user_id=request.admin_user.id
        ).all()
        notifications = {}
        for notif in notification_settings:
            notifications[notif.notification_type] = notif.enabled

        # Obtener configuración de seguridad
        security_settings = SecuritySetting.query.all()
        security = {}
        for setting in security_settings:
            if setting.value_type == 'number':
                security[setting.key] = float(setting.value)
            elif setting.value_type == 'boolean':
                security[setting.key] = setting.value.lower() in ('true', '1', 'yes', 'on')
            else:
                security[setting.key] = setting.value

        # Obtener configuración general
        general_settings = SystemSettings.query.filter_by(category='general').all()
        general = {}
        for setting in general_settings:
            key = setting.key.replace('general.', '')
            if setting.value_type == 'number':
                general[key] = float(setting.value)
            elif setting.value_type == 'boolean':
                general[key] = setting.value.lower() in ('true', '1', 'yes', 'on')
            else:
                general[key] = setting.value

        return jsonify({
            'success': True,
            'data': {
                'wallet': wallet_config,
                'messages': messages,
                'notifications': notifications,
                'security': security,
                'general': general
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@settings_bp.route('/settings/wallet', methods=['PUT'])
@admin_required
def update_wallet_settings():
    """
    Actualizar configuración de billetera
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400

        # Mapeo de campos del frontend a keys de la base de datos
        wallet_mappings = {
            'montoFijo': ('wallet.fixed_amount', 'number', 'Monto fijo de Pesos Bausing por compra'),
            'montoMinimo': ('wallet.min_amount', 'number', 'Monto mínimo de compra para acreditar Pesos Bausing'),
            'porcentajeMaximo': ('wallet.max_usage_percentage', 'number', 'Porcentaje máximo de uso de billetera por compra'),
            'vencimiento': ('wallet.expiration_days', 'number', 'Vencimiento de Pesos Bausing en días'),
            'permitirAcumulacion': ('wallet.allow_accumulation', 'boolean', 'Permitir acumulación de Pesos Bausing')
        }

        updated_settings = []
        for key, value in data.items():
            if key in wallet_mappings:
                db_key, value_type, description = wallet_mappings[key]
                setting = SystemSettings.set_value(
                    key=db_key,
                    value=value,
                    value_type=value_type,
                    category='wallet',
                    description=description,
                    updated_by=request.admin_user.id
                )
                updated_settings.append(setting.to_dict())

        db.session.commit()

        return jsonify({
            'success': True,
            'data': updated_settings,
            'message': 'Configuración de billetera actualizada correctamente'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@settings_bp.route('/settings/messages', methods=['PUT'])
@admin_required
def update_message_templates():
    """
    Actualizar plantillas de mensajes automáticos
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400

        # Mapeo de tipos de mensajes
        message_mappings = {
            'acreditacion': {
                'type': 'wallet_accreditation',
                'subject': 'Pesos Bausing Acreditados',
                'variables': ['nombre', 'monto', 'pedido']
            },
            'confirmacion': {
                'type': 'order_confirmation',
                'subject': 'Confirmación de Pedido',
                'variables': ['nombre', 'pedido', 'total']
            },
            'enCamino': {
                'type': 'order_shipping',
                'subject': 'Tu Pedido Está en Reparto',
                'variables': ['nombre', 'pedido', 'tracking']
            }
        }

        updated_templates = []
        for key, value in data.items():
            if key in message_mappings:
                mapping = message_mappings[key]
                template = MessageTemplate.query.filter_by(type=mapping['type']).first()
                
                if template:
                    template.body = value
                    template.subject = mapping['subject']
                    template.variables = mapping['variables']
                    template.updated_by = request.admin_user.id
                    template.updated_at = datetime.utcnow()
                else:
                    template = MessageTemplate(
                        type=mapping['type'],
                        subject=mapping['subject'],
                        body=value,
                        variables=mapping['variables'],
                        is_active=True,
                        updated_by=request.admin_user.id
                    )
                    db.session.add(template)
                
                updated_templates.append(template.to_dict())

        db.session.commit()

        return jsonify({
            'success': True,
            'data': updated_templates,
            'message': 'Plantillas de mensajes actualizadas correctamente'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@settings_bp.route('/settings/notifications', methods=['PUT'])
@admin_required
def update_notification_settings():
    """
    Actualizar configuración de notificaciones para el usuario admin actual
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400

        # Tipos de notificaciones disponibles
        notification_types = [
            'new_orders',
            'payment_errors',
            'low_stock',
            'unusual_movements',
            'customer_complaints'
        ]

        updated_settings = []
        for notif_type, enabled in data.items():
            # Mapear nombres del frontend a tipos de notificación
            type_mapping = {
                'nuevosPedidos': 'new_orders',
                'erroresPagos': 'payment_errors',
                'stockBajo': 'low_stock',
                'movimientosInusuales': 'unusual_movements',
                'reclamosClientes': 'customer_complaints'
            }
            
            if notif_type in type_mapping:
                db_notif_type = type_mapping[notif_type]
                
                # Buscar o crear configuración
                setting = NotificationSetting.query.filter_by(
                    admin_user_id=request.admin_user.id,
                    notification_type=db_notif_type,
                    channel='email'  # Por defecto email
                ).first()
                
                if setting:
                    setting.enabled = enabled
                    setting.updated_at = datetime.utcnow()
                else:
                    setting = NotificationSetting(
                        admin_user_id=request.admin_user.id,
                        notification_type=db_notif_type,
                        enabled=enabled,
                        channel='email'
                    )
                    db.session.add(setting)
                
                updated_settings.append(setting.to_dict())

        db.session.commit()

        return jsonify({
            'success': True,
            'data': updated_settings,
            'message': 'Configuración de notificaciones actualizada correctamente'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@settings_bp.route('/settings/security', methods=['PUT'])
@admin_required
def update_security_settings():
    """
    Actualizar configuración de seguridad
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400

        # Mapeo de campos del frontend a keys de la base de datos
        security_mappings = {
            'montoMaximoCarga': ('max_manual_wallet_load', 'number'),
            'registrarCambios': ('require_audit_log', 'boolean'),
            'comentarioObligatorio': ('require_comment_on_adjustments', 'boolean')
        }

        updated_settings = []
        for key, value in data.items():
            if key in security_mappings:
                db_key, value_type = security_mappings[key]
                setting = SecuritySetting.set_value(
                    key=db_key,
                    value=value,
                    value_type=value_type,
                    updated_by=request.admin_user.id
                )
                updated_settings.append(setting.to_dict())

        db.session.commit()

        return jsonify({
            'success': True,
            'data': updated_settings,
            'message': 'Configuración de seguridad actualizada correctamente'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@settings_bp.route('/settings/general', methods=['PUT'])
@admin_required
def update_general_settings():
    """
    Actualizar configuración general
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400

        # Mapeo de campos del frontend a keys de la base de datos
        general_mappings = {
            'telefono': ('general.phone', 'string', 'Número de teléfono de Bausing')
        }

        updated_settings = []
        for key, value in data.items():
            if key in general_mappings:
                db_key, value_type, description = general_mappings[key]
                setting = SystemSettings.set_value(
                    key=db_key,
                    value=value,
                    value_type=value_type,
                    category='general',
                    description=description,
                    updated_by=request.admin_user.id
                )
                updated_settings.append(setting.to_dict())

        db.session.commit()

        return jsonify({
            'success': True,
            'data': updated_settings,
            'message': 'Configuración general actualizada correctamente'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

