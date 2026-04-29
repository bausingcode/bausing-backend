from flask import Blueprint, request, jsonify
from database import db
from models.settings import SystemSettings, MessageTemplate, NotificationSetting, SecuritySetting
from routes.admin import admin_required
from datetime import datetime
import uuid as uuid_lib

settings_bp = Blueprint('settings', __name__)
public_settings_bp = Blueprint('public_settings', __name__)


def _resolve_root_category_uuid(leaf_category_id_str):
    """UUID de categoría raíz (sin padre) a partir de una categoría hoja, o None."""
    from models.category import Category

    try:
        uid = uuid_lib.UUID(str(leaf_category_id_str).strip())
    except Exception:
        return None
    cat = Category.query.get(uid)
    if not cat:
        return None
    cur = cat
    steps = 0
    while cur.parent_id is not None and steps < 32:
        parent = Category.query.get(cur.parent_id)
        if not parent:
            break
        cur = parent
        steps += 1
    return cur.id


def _pdp_cross_sell_by_category_from_db():
    from models.category_pdp_cross_sell import CategoryPdpCrossSell

    rows = CategoryPdpCrossSell.query.all()
    by_category = {}
    for r in rows:
        ids = r.ordered_product_ids()
        if ids:
            by_category[str(r.category_id)] = ids
    return by_category


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


@public_settings_bp.route('/settings/public/footer', methods=['GET'])
def get_public_footer():
    """
    Obtener datos de contacto del footer (sin autenticación)
    """
    try:
        settings = SystemSettings.query.filter(
            SystemSettings.key.in_([
                'general.phone',
                'general.email',
                'general.address',
                'general.instagram_url',
                'general.facebook_url',
                'general.tiktok_url'
            ])
        ).all()
        
        footer_data = {
            'phone': None,
            'email': None,
            'address': None,
            'instagram_url': None,
            'facebook_url': None,
            'tiktok_url': None
        }
        
        for setting in settings:
            key = setting.key.replace('general.', '')
            if key == 'phone':
                footer_data['phone'] = setting.value
            elif key == 'email':
                footer_data['email'] = setting.value
            elif key == 'address':
                footer_data['address'] = setting.value
            elif key == 'instagram_url':
                footer_data['instagram_url'] = setting.value
            elif key == 'facebook_url':
                footer_data['facebook_url'] = setting.value
            elif key == 'tiktok_url':
                footer_data['tiktok_url'] = setting.value
        
        return jsonify({
            'success': True,
            'data': footer_data
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@public_settings_bp.route('/settings/public/pdp-cross-sell', methods=['GET'])
def get_public_pdp_cross_sell():
    """
    PDP "Completa tu compra" (público). Hasta 2 productos por categoría principal.

    - Sin query: { by_category: { "<main_cat_uuid>": ["prod", ...] } }.
    - Con ?leaf_category_id=<uuid>: { product_ids, resolved_main_category_id }.
    """
    try:
        from models.category_pdp_cross_sell import CategoryPdpCrossSell

        leaf = request.args.get('leaf_category_id', '').strip()
        if leaf:
            main_uid = _resolve_root_category_uuid(leaf)
            if not main_uid:
                return jsonify({
                    'success': True,
                    'data': {
                        'product_ids': [],
                        'resolved_main_category_id': None,
                    },
                }), 200
            row = CategoryPdpCrossSell.query.filter_by(category_id=main_uid).first()
            pids = row.ordered_product_ids() if row else []
            return jsonify({
                'success': True,
                'data': {
                    'product_ids': pids,
                    'resolved_main_category_id': str(main_uid),
                },
            }), 200

        by_category = _pdp_cross_sell_by_category_from_db()
        return jsonify({'success': True, 'data': {'by_category': by_category}}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@public_settings_bp.route('/settings/public/price-per-km', methods=['GET'])
def get_public_price_per_km():
    """
    Obtener precio por kilómetro de envío (sin autenticación)
    """
    try:
        price_setting = SystemSettings.query.filter_by(key='general.price_per_km').first()
        
        if price_setting and price_setting.value_type == 'number':
            try:
                price = float(price_setting.value)
                return jsonify({
                    'success': True,
                    'price_per_km': price
                }), 200
            except ValueError:
                pass
        
        # Valor por defecto si no está configurado
        return jsonify({
            'success': True,
            'price_per_km': 105
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


@settings_bp.route('/settings/pdp-cross-sell', methods=['GET'])
@admin_required
def get_pdp_cross_sell_admin():
    """Misma forma que público (sin leaf); para pantalla admin."""
    try:
        by_category = _pdp_cross_sell_by_category_from_db()
        return jsonify({'success': True, 'data': {'by_category': by_category}}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/settings/pdp-cross-sell', methods=['PUT'])
@admin_required
def update_pdp_cross_sell():
    """
    Body: { "by_category": { "<category_uuid>": ["prod_uuid", ...], ... } }
    Solo categorías principales (sin parent_id). Máximo 2 productos por categoría.
    Persistido en tabla category_pdp_cross_sell (product_id_3 queda en NULL).
    """
    try:
        data = request.get_json()
        if not data or 'by_category' not in data:
            return jsonify({'success': False, 'error': 'by_category requerido'}), 400
        incoming = data['by_category']
        if incoming is not None and not isinstance(incoming, dict):
            return jsonify({'success': False, 'error': 'by_category debe ser un objeto'}), 400

        from models.category import Category
        from models.product import Product
        from models.category_pdp_cross_sell import CategoryPdpCrossSell

        normalized = {}
        if isinstance(incoming, dict):
            for cat_key, val in incoming.items():
                if cat_key is None:
                    continue
                cat_s = str(cat_key).strip()
                if not cat_s:
                    continue
                try:
                    cat_uuid = str(uuid_lib.UUID(cat_s))
                except Exception:
                    return jsonify({
                        'success': False,
                        'error': f'ID de categoría inválido: {cat_s}',
                    }), 400

                main = Category.query.get(uuid_lib.UUID(cat_uuid))
                if not main:
                    return jsonify({
                        'success': False,
                        'error': f'Categoría no encontrada: {cat_uuid}',
                    }), 404
                if main.parent_id is not None:
                    return jsonify({
                        'success': False,
                        'error': f'Solo categorías principales (sin padre): {main.name}',
                    }), 400

                id_list = []
                if isinstance(val, list):
                    iter_v = val
                elif val is None or (isinstance(val, str) and not val.strip()):
                    iter_v = []
                else:
                    iter_v = [val]

                seen = set()
                for x in iter_v:
                    if len(id_list) >= 2:
                        break
                    if x is None:
                        continue
                    pid = str(x).strip()
                    if not pid or pid in seen:
                        continue
                    try:
                        pid = str(uuid_lib.UUID(pid))
                    except Exception:
                        return jsonify({
                            'success': False,
                            'error': f'ID de producto inválido: {pid}',
                        }), 400
                    prod = Product.query.get(uuid_lib.UUID(pid))
                    if not prod:
                        return jsonify({
                            'success': False,
                            'error': f'Producto no encontrado: {pid}',
                        }), 404
                    seen.add(pid)
                    id_list.append(pid)

                if id_list:
                    normalized[cat_uuid] = id_list

        existing_ids = {str(r.category_id) for r in CategoryPdpCrossSell.query.all()}
        incoming_keys = set(normalized.keys())
        for cid_str in existing_ids - incoming_keys:
            CategoryPdpCrossSell.query.filter_by(
                category_id=uuid_lib.UUID(cid_str),
            ).delete(synchronize_session=False)

        admin_uid = request.admin_user.id
        for cat_uuid_str, id_list in normalized.items():
            uid_cat = uuid_lib.UUID(cat_uuid_str)
            p1 = uuid_lib.UUID(id_list[0]) if len(id_list) > 0 else None
            p2 = uuid_lib.UUID(id_list[1]) if len(id_list) > 1 else None
            row = CategoryPdpCrossSell.query.filter_by(category_id=uid_cat).first()
            if row:
                row.product_id_1 = p1
                row.product_id_2 = p2
                row.product_id_3 = None
                row.updated_by = admin_uid
            else:
                db.session.add(CategoryPdpCrossSell(
                    category_id=uid_cat,
                    product_id_1=p1,
                    product_id_2=p2,
                    product_id_3=None,
                    updated_by=admin_uid,
                ))

        db.session.commit()

        return jsonify({
            'success': True,
            'data': {'by_category': normalized},
            'message': 'Configuración actualizada',
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


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
            'telefono': ('general.phone', 'string', 'Número de teléfono de Bausing'),
            'diasEstimadosEnvio': ('general.estimated_shipping_days', 'number', 'Días estimados para envío de pedidos'),
            'email': ('general.email', 'string', 'Email de contacto de Bausing'),
            'direccion': ('general.address', 'string', 'Dirección física de Bausing'),
            'instagramUrl': ('general.instagram_url', 'string', 'URL de Instagram'),
            'facebookUrl': ('general.facebook_url', 'string', 'URL de Facebook'),
            'tiktokUrl': ('general.tiktok_url', 'string', 'URL de TikTok'),
            'precioPorKm': ('general.price_per_km', 'number', 'Precio por kilómetro de envío')
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

