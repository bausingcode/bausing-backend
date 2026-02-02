from flask import Blueprint, request, jsonify, current_app
from database import db
from models.order import Order
from models.address import Address
from models.doc_type import DocType
from models.province import Province
from models.crm_province import CrmProvinceMap, CrmProvince
from models.crm_delivery_zone import CrmZoneLocality, CrmDeliveryZone
from models.locality import Locality
from models.product import Product, ProductVariant, ProductVariantOption
from sqlalchemy import desc, func, text
from sqlalchemy.exc import IntegrityError
from routes.auth import user_required
from config import Config
import uuid
from datetime import datetime
import re
import json
import os
import requests

orders_bp = Blueprint('orders', __name__)

# Funciones helper para obtener IDs del CRM
def get_crm_zone_id_from_locality(locality_name):
    """
    Obtiene el crm_zone_id desde el nombre de la localidad
    Busca en crm_zone_localities la localidad por nombre y retorna el crm_zone_id
    Si no encuentra mapeo, busca en crm_delivery_zones por nombre y crea el mapeo automáticamente
    """
    try:
        print(f"[DEBUG] get_crm_zone_id_from_locality: Buscando localidad con nombre: '{locality_name}'")
        
        # Hacer rollback de cualquier transacción abortada
        try:
            db.session.rollback()
        except:
            pass
        
        # Buscar la localidad por nombre exacto
        print(f"[DEBUG] Buscando localidad con nombre exacto: '{locality_name}'")
        locality = Locality.query.filter_by(name=locality_name).first()
        
        if not locality:
            # Intentar búsqueda case-insensitive
            print(f"[DEBUG] No se encontró con nombre exacto, intentando búsqueda case-insensitive...")
            locality = Locality.query.filter(Locality.name.ilike(locality_name)).first()
        
        if not locality:
            # Intentar búsqueda parcial
            print(f"[DEBUG] No se encontró con búsqueda case-insensitive, intentando búsqueda parcial...")
            locality = Locality.query.filter(Locality.name.ilike(f'%{locality_name}%')).first()
        
        if not locality:
            # Listar todas las localidades disponibles para debug
            print(f"[DEBUG] No se encontró localidad. Listando todas las localidades disponibles:")
            all_localities = Locality.query.all()
            for loc in all_localities[:10]:  # Mostrar solo las primeras 10
                print(f"  - {loc.name} (id: {loc.id})")
            if len(all_localities) > 10:
                print(f"  ... y {len(all_localities) - 10} más")
            print(f"❌ No se encontró localidad con nombre: '{locality_name}'")
            return None
        
        print(f"[DEBUG] ✅ Localidad encontrada: {locality.name} (id: {locality.id})")
        
        # Primero intentar buscar en crm_zone_localities
        try:
            zone_locality = CrmZoneLocality.query.filter_by(locality_id=locality.id).first()
            if zone_locality:
                return zone_locality.crm_zone_id
        except Exception as e:
            print(f"Error al buscar en crm_zone_localities: {str(e)}")
            db.session.rollback()
        
        # Si no hay mapeo, intentar buscar en crm_delivery_zones por nombre
        try:
            # Buscar zona por nombre (puede que el nombre de la zona coincida con el nombre de la localidad)
            crm_zone = CrmDeliveryZone.query.filter(
                CrmDeliveryZone.name.ilike(f'%{locality_name}%'),
                CrmDeliveryZone.crm_deleted_at.is_(None)
            ).first()
            
            if crm_zone:
                # Crear el mapeo automáticamente
                try:
                    new_mapping = CrmZoneLocality(
                        crm_zone_id=crm_zone.crm_zone_id,
                        locality_id=locality.id
                    )
                    db.session.add(new_mapping)
                    db.session.commit()
                    print(f"✅ Creado mapeo automático en crm_zone_localities: localidad {locality_name} (id: {locality.id}) -> crm_zone_id {crm_zone.crm_zone_id}")
                except Exception as mapping_error:
                    # Si falla la creación del mapeo (por ejemplo, ya existe), hacer rollback y continuar
                    db.session.rollback()
                    print(f"⚠️  No se pudo crear mapeo automático (puede que ya exista): {str(mapping_error)}")
                
                return crm_zone.crm_zone_id
            else:
                print(f"❌ No se encontró zona de entrega para localidad {locality_name} en crm_delivery_zones")
        except Exception as e:
            print(f"Error al buscar zona de entrega: {str(e)}")
            db.session.rollback()
        
        return None
    except Exception as e:
        print(f"Error al obtener crm_zone_id desde localidad: {str(e)}")
        import traceback
        print(traceback.format_exc())
        try:
            db.session.rollback()
        except:
            pass
        return None

def get_crm_province_id_from_province(province_id):
    """
    Obtiene el crm_province_id desde el province_id
    Busca en crm_province_map el mapeo, y si no existe, busca por nombre en crm_provinces
    """
    try:
        # Hacer rollback de cualquier transacción abortada
        try:
            db.session.rollback()
        except:
            pass
        
        province_uuid = uuid.UUID(province_id) if isinstance(province_id, str) else province_id
        
        # Primero intentar buscar en crm_province_map
        try:
            province_map = CrmProvinceMap.query.filter_by(province_id=province_uuid).first()
            if province_map:
                return province_map.crm_province_id
        except Exception as e:
            print(f"Error al buscar en crm_province_map: {str(e)}")
            db.session.rollback()
        
        # Si no hay mapeo, intentar buscar por nombre de provincia
        try:
            province = Province.query.get(province_uuid)
            if province:
                # Buscar en crm_provinces por nombre
                crm_province = CrmProvince.query.filter_by(name=province.name).first()
                if crm_province:
                    # Crear el mapeo automáticamente para evitar búsquedas futuras
                    try:
                        new_mapping = CrmProvinceMap(
                            crm_province_id=crm_province.crm_province_id,
                            province_id=province_uuid
                        )
                        db.session.add(new_mapping)
                        db.session.commit()
                        print(f"✅ Creado mapeo automático en crm_province_map: provincia {province.name} (id: {province_uuid}) -> crm_province_id {crm_province.crm_province_id}")
                    except Exception as mapping_error:
                        # Si falla la creación del mapeo (por ejemplo, ya existe), hacer rollback y continuar
                        db.session.rollback()
                        print(f"⚠️  No se pudo crear mapeo automático (puede que ya exista): {str(mapping_error)}")
                    
                    return crm_province.crm_province_id
                else:
                    print(f"❌ No se encontró provincia {province.name} en crm_provinces")
            else:
                print(f"❌ No se encontró provincia con id {province_id}")
        except Exception as e:
            print(f"Error al buscar provincia: {str(e)}")
            db.session.rollback()
        
        return None
    except Exception as e:
        print(f"Error al obtener crm_province_id desde province_id: {str(e)}")
        import traceback
        print(traceback.format_exc())
        try:
            db.session.rollback()
        except:
            pass
        return None

def get_crm_doc_type_id_from_doc_type(doc_type_id):
    """
    Obtiene el crm_doc_type_id desde el doc_type_id
    El modelo DocType ya tiene el campo crm_doc_type_id
    """
    try:
        doc_type_uuid = uuid.UUID(doc_type_id) if isinstance(doc_type_id, str) else doc_type_id
        doc_type = DocType.query.get(doc_type_uuid)
        if doc_type and doc_type.crm_doc_type_id:
            # crm_doc_type_id es UUID, pero necesitamos el integer del CRM
            # Por ahora retornamos None y lo manejaremos después
            # TODO: Necesitamos una tabla de mapeo similar a crm_province_map
            return None
        return None
    except Exception as e:
        print(f"Error al obtener crm_doc_type_id desde doc_type_id: {str(e)}")
        return None

def format_document_number(doc_type_id, document_number, crm_sale_type_id):
    """
    Formatea el número de documento según el tipo de venta
    Si es Responsable Inscripto (crm_sale_type_id = 4), formatea como CUIT: XX-XXXXXXXX-X
    """
    if crm_sale_type_id == 4:  # Responsable Inscripto
        # Formato CUIT: XX-XXXXXXXX-X
        # Remover guiones y espacios existentes
        cleaned = re.sub(r'[-\s]', '', str(document_number))
        if len(cleaned) == 11:
            return f"{cleaned[:2]}-{cleaned[2:10]}-{cleaned[10]}"
        return document_number
    return document_number

@orders_bp.route('/orders', methods=['GET'])
@user_required
def get_user_orders():
    """
    Obtener todas las órdenes del usuario autenticado
    
    Query parameters:
    - page: número de página (default: 1)
    - per_page: items por página (default: 50, max: 100)
    - status: filtrar por estado (pending, in_transit, pending_delivery, delivered, cancelled)
    """
    try:
        user = request.user
        
        # Paginación
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)
        status_filter = request.args.get('status')
        
        # Query base
        query = Order.query.filter_by(user_id=user.id)
        
        # Filtro por estado
        if status_filter:
            query = query.filter_by(status=status_filter)
        
        # Ordenar por fecha descendente (más recientes primero)
        query = query.order_by(desc(Order.created_at))
        
        # Paginación
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        orders = pagination.items
        
        # Convertir órdenes a formato esperado por el frontend
        orders_data = []
        for order in orders:
            order_dict = order_to_dict(order)
            orders_data.append(order_dict)
        
        return jsonify({
            'success': True,
            'data': {
                'orders': orders_data,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': pagination.total,
                    'pages': pagination.pages
                }
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error al obtener órdenes: {str(e)}'
        }), 500


@orders_bp.route('/orders/<order_id>', methods=['GET'])
@user_required
def get_user_order(order_id):
    """
    Obtener una orden específica del usuario autenticado
    """
    try:
        user = request.user
        
        # Validar que el order_id sea un UUID válido
        try:
            order_uuid = uuid.UUID(order_id)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'ID de orden inválido'
            }), 400
        
        # Buscar la orden
        order = Order.query.filter_by(id=order_uuid, user_id=user.id).first()
        
        if not order:
            return jsonify({
                'success': False,
                'error': 'Orden no encontrada'
            }), 404
        
        # Convertir orden a formato esperado por el frontend
        order_dict = order_to_dict(order)
        
        return jsonify({
            'success': True,
            'data': order_dict
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error al obtener orden: {str(e)}'
        }), 500


def order_to_dict(order):
    """
    Convierte una orden del modelo a el formato esperado por el frontend
    """
    from sqlalchemy import text
    
    # Obtener la dirección de envío (si existe)
    shipping_address = None
    # Por ahora, obtenemos la primera dirección del usuario como dirección de envío
    # En el futuro, esto debería venir de una tabla order_addresses o similar
    address = Address.query.filter_by(user_id=order.user_id).first()
    if address:
        shipping_address = address.to_dict()
    
    # Obtener items de la orden
    # Por ahora, como no hay tabla order_items, retornamos un array vacío
    # En el futuro, esto debería venir de una tabla order_items
    items = []
    
    # Determinar payment_status basado en el status de la orden
    payment_status = "pending"
    if order.status in ["in_transit", "pending_delivery", "delivered"]:
        payment_status = "paid"
    elif order.status == "cancelled":
        payment_status = "failed"
    
    # Determinar pay_on_delivery
    pay_on_delivery = order.payment_method == "cash" and payment_status == "pending"
    
    # Obtener receipt_number desde crm_orders usando crm_order_id
    order_number = None
    if hasattr(order, 'crm_order_id') and order.crm_order_id:
        try:
            receipt_query = text("""
                SELECT receipt_number 
                FROM crm_orders 
                WHERE crm_order_id = :crm_order_id
            """)
            receipt_result = db.session.execute(receipt_query, {
                'crm_order_id': order.crm_order_id
            })
            receipt_row = receipt_result.fetchone()
            if receipt_row and receipt_row[0]:
                order_number = receipt_row[0]
        except Exception:
            pass
    
    # Si no se encontró receipt_number, usar valor por defecto
    if not order_number:
        order_number = f"ORD-{order.created_at.strftime('%Y')}-{str(order.id)[:8].upper()}"
    
    return {
        'id': str(order.id),
        'user_id': str(order.user_id),
        'order_number': order_number,
        'status': order.status,
        'payment_method': order.payment_method or 'card',
        'payment_status': payment_status,
        'payment_processed': order.payment_processed if hasattr(order, 'payment_processed') else False,
        'pay_on_delivery': pay_on_delivery,
        'total_amount': float(order.total) if order.total else 0.0,
        'shipping_address': shipping_address,
        'items': items,
        'tracking_number': None,  # Por ahora None, se puede agregar después
        'tracking_url': None,  # Por ahora None, se puede agregar después
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'updated_at': order.created_at.isoformat() if order.created_at else None  # Por ahora usamos created_at
    }

@orders_bp.route('/orders', methods=['POST'])
@user_required
def create_order():
    """
    Crear una nueva orden
    Si pay_on_delivery is true, primero crea la venta en el CRM
    """
    try:
        # Limpiar cualquier transacción abortada
        try:
            db.session.rollback()
        except:
            pass
        
        user = request.user
        data = request.get_json()
        
        print(f"[DEBUG] ========== CREAR ORDEN ==========")
        print(f"[DEBUG] User ID: {user.id}")
        print(f"[DEBUG] Data recibida: {json.dumps(data, indent=2, default=str)}")
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400
        
        # Validar campos requeridos
        required_fields = ['address', 'items', 'payment_method', 'total']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'El campo {field} es requerido'
                }), 400
        
        pay_on_delivery = data.get('pay_on_delivery', False)
        crm_sale_type_id = data.get('crm_sale_type_id', 1)  # Default: Consumidor Final
        address_data = data['address']
        items = data['items']
        total = float(data['total'])
        formData = data.get('customer', {})  # Datos del cliente para el pago
        payment_method = data.get('payment_method', 'card')
        
        # Si es pago con tarjeta, verificar que MP_ACCESS_TOKEN esté configurado ANTES de crear la orden
        if payment_method == 'card' and not pay_on_delivery:
            mp_access_token = Config.MP_ACCESS_TOKEN or os.getenv('MP_ACCESS_TOKEN')
            if not mp_access_token:
                print("[DEBUG] ⚠️ MP_ACCESS_TOKEN no configurado - abortando creación de orden")
                return jsonify({
                    'success': False,
                    'error': 'Configuración de pago no disponible. Por favor, contacta al soporte.'
                }), 500
        
        print(f"[DEBUG] pay_on_delivery: {pay_on_delivery}")
        print(f"[DEBUG] crm_sale_type_id: {crm_sale_type_id}")
        print(f"[DEBUG] total: {total}")
        print(f"[DEBUG] payment_method: {data.get('payment_method')}")
        print(f"[DEBUG] crm_zone_id recibido: {data.get('crm_zone_id')}")
        print(f"[DEBUG] wallet_amount recibido: {data.get('wallet_amount')}")
        print(f"[DEBUG] used_wallet_amount recibido: {data.get('used_wallet_amount')}")
        
        crm_order_id = None
        
        # Si es "abonar al recibir", crear venta en CRM primero
        if pay_on_delivery:
            try:
                # Obtener datos del usuario
                customer_data = data.get('customer', {})
                first_name = customer_data.get('first_name') or user.first_name or ''
                last_name = customer_data.get('last_name') or user.last_name or ''
                email = customer_data.get('email') or user.email or ''
                phone = customer_data.get('phone') or user.phone or address_data.get('phone') or ''
                alternate_phone = customer_data.get('alternate_phone') or None
                
                print(f"[DEBUG] Datos del cliente: first_name={first_name}, last_name={last_name}, email={email}, phone={phone}")
                
                # Función para normalizar y validar teléfono
                def normalize_phone(phone_str):
                    if not phone_str:
                        return "3510000000"  # Teléfono por defecto
                    
                    # Convertir a string y limpiar espacios
                    phone_str = str(phone_str).strip()
                    
                    # Remover caracteres no numéricos (excepto + al inicio)
                    phone_cleaned = ''.join(c for c in phone_str if c.isdigit())
                    
                    # Quitar prefijos comunes
                    if phone_cleaned.startswith('0'):
                        phone_cleaned = phone_cleaned[1:]
                    elif phone_cleaned.startswith('150'):
                        phone_cleaned = phone_cleaned[3:]
                    elif phone_cleaned.startswith('15'):
                        phone_cleaned = phone_cleaned[2:]
                    
                    # Validar formato: debe tener entre 8 y 11 dígitos (código de área + número)
                    # En Argentina: código de área (2-4 dígitos) + número (6-8 dígitos) = 8-12 dígitos total
                    # Pero típicamente son 10 dígitos (2-3 código + 7-8 número)
                    if len(phone_cleaned) < 8 or len(phone_cleaned) > 11:
                        print(f"[DEBUG] Teléfono no tiene formato válido (longitud: {len(phone_cleaned)}), usando default: 3510000000")
                        return "3510000000"
                    
                    # Verificar que sean solo dígitos
                    if not phone_cleaned.isdigit():
                        print(f"[DEBUG] Teléfono contiene caracteres no numéricos, usando default: 3510000000")
                        return "3510000000"
                    
                    return phone_cleaned
                
                # Normalizar teléfono principal
                phone = normalize_phone(phone)
                print(f"[DEBUG] Teléfono normalizado: '{phone}'")
                
                # Normalizar teléfono alternativo
                if alternate_phone:
                    alternate_phone = normalize_phone(alternate_phone)
                    print(f"[DEBUG] Teléfono alternativo normalizado: '{alternate_phone}'")
                
                # Debug del teléfono
                print(f"[DEBUG] Teléfono - customer_data.phone: {customer_data.get('phone')}")
                print(f"[DEBUG] Teléfono - user.phone: {user.phone}")
                print(f"[DEBUG] Teléfono - address_data.phone: {address_data.get('phone')}")
                print(f"[DEBUG] Teléfono - Final phone value (después de limpiar): '{phone}'")
                print(f"[DEBUG] Teléfono - Type: {type(phone)}")
                print(f"[DEBUG] Teléfono - Length: {len(phone) if phone else 0}")
                if phone:
                    print(f"[DEBUG] Teléfono - Characters: {[c for c in phone]}")
                    print(f"[DEBUG] Teléfono - Is digit: {phone.isdigit() if isinstance(phone, str) else 'N/A'}")
                
                # Obtener tipo de documento
                doc_type_id = customer_data.get('document_type') or customer_data.get('doc_type_id')
                document_number = customer_data.get('dni') or customer_data.get('document_number')
                
                if not doc_type_id or not document_number:
                    return jsonify({
                        'success': False,
                        'error': 'Tipo de documento y número de documento son requeridos'
                    }), 400
                
                # Obtener doc_type para el crm_doc_type_id
                doc_type = DocType.query.get(uuid.UUID(doc_type_id) if isinstance(doc_type_id, str) else doc_type_id)
                if not doc_type:
                    return jsonify({
                        'success': False,
                        'error': 'Tipo de documento no encontrado'
                    }), 400
                
                # Obtener el crm_doc_type_id (integer) desde la tabla crm_doc_types
                # Por ahora usamos un valor por defecto si no hay mapeo
                # TODO: Crear tabla de mapeo similar a crm_province_map
                crm_doc_type_id_int = None
                if doc_type.crm_doc_type_id:
                    # Buscar en crm_doc_types el integer correspondiente al UUID
                    query_doc_type = text("""
                        SELECT crm_doc_type_id 
                        FROM crm_doc_types 
                        WHERE id = :doc_type_uuid
                        LIMIT 1
                    """)
                    try:
                        result = db.session.execute(query_doc_type, {
                            'doc_type_uuid': str(doc_type.crm_doc_type_id)
                        })
                        row = result.fetchone()
                        if row:
                            crm_doc_type_id_int = row[0]
                            print(f"[DEBUG] ✅ crm_doc_type_id encontrado: {crm_doc_type_id_int} para doc_type: {doc_type.name} (UUID: {doc_type.crm_doc_type_id})")
                    except Exception as e:
                        print(f"[DEBUG] ⚠️ Error al buscar crm_doc_type_id: {str(e)}")
                        pass
                
                # Si no se encontró, intentar determinar por el nombre del tipo de documento
                if not crm_doc_type_id_int:
                    doc_type_name_lower = doc_type.name.lower() if doc_type.name else ""
                    if 'cuit' in doc_type_name_lower or 'cuil' in doc_type_name_lower:
                        crm_doc_type_id_int = 2  # CUIT/CUIL
                        print(f"[DEBUG] ℹ️  Usando crm_doc_type_id=2 (CUIT/CUIL) basado en nombre: {doc_type.name}")
                    else:
                        crm_doc_type_id_int = 1  # DNI por defecto
                        print(f"[DEBUG] ⚠️  No se encontró crm_doc_type_id, usando valor por defecto 1 (DNI) para doc_type: {doc_type.name}")
                
                print(f"[DEBUG] crm_doc_type_id_int final: {crm_doc_type_id_int}")
                
                # Formatear documento según tipo de venta
                formatted_document = format_document_number(doc_type_id, document_number, crm_sale_type_id)
                print(f"[DEBUG] Documento formateado: '{formatted_document}' (tipo: {crm_doc_type_id_int}, original: '{document_number}')")
                
                # Obtener provincia y zona
                province_id = address_data.get('province_id')
                if not province_id:
                    return jsonify({
                        'success': False,
                        'error': 'province_id es requerido en la dirección'
                    }), 400
                
                crm_province_id = get_crm_province_id_from_province(province_id)
                if not crm_province_id:
                    return jsonify({
                        'success': False,
                        'error': 'No se pudo obtener crm_province_id para la provincia seleccionada'
                    }), 400
                
                city = address_data.get('city')
                # Usar crm_zone_id del request si está disponible, sino buscarlo por localidad
                crm_zone_id = data.get('crm_zone_id')
                if not crm_zone_id:
                    crm_zone_id = get_crm_zone_id_from_locality(city)
                    if not crm_zone_id:
                        return jsonify({
                            'success': False,
                            'error': f'No se pudo obtener crm_zone_id para la localidad: {city}'
                        }), 400
                
                # Construir dirección completa
                street = address_data.get('street', '')
                number = address_data.get('number', '')
                additional_info = address_data.get('additional_info', '')
                postal_code = address_data.get('postal_code', '')
                
                cliente_direccion = f"{street} {number}".strip()
                cliente_direccion_barrio = city
                cliente_direccion_mas_datos = additional_info if additional_info else None
                
                # Preparar items para el CRM
                js_items = []
                items_without_crm_id = []
                
                for item in items:
                    product_id = uuid.UUID(item['product_id']) if isinstance(item['product_id'], str) else item['product_id']
                    print(f"[DEBUG] Procesando item: product_id={product_id}, quantity={item.get('quantity')}")
                    
                    product = Product.query.get(product_id)
                    if not product:
                        print(f"[DEBUG] ❌ Producto no encontrado: {product_id}")
                        items_without_crm_id.append(f"Producto {product_id} no encontrado")
                        continue
                    
                    print(f"[DEBUG] ✅ Producto encontrado: {product.name}, crm_product_id={product.crm_product_id}")
                    
                    # Obtener el primer variant y option del producto
                    variant = ProductVariant.query.filter_by(product_id=product_id).first()
                    if not variant:
                        print(f"[DEBUG] ❌ No se encontró variant para producto {product_id}")
                        items_without_crm_id.append(f"Producto {product.name}: sin variantes")
                        continue
                    
                    print(f"[DEBUG] ✅ Variant encontrado: id={variant.id}, sku={variant.sku}")
                    
                    option = ProductVariantOption.query.filter_by(product_variant_id=variant.id).first()
                    if not option:
                        print(f"[DEBUG] ❌ No se encontró option para variant {variant.id}")
                        items_without_crm_id.append(f"Producto {product.name}: sin opciones")
                        continue
                    
                    print(f"[DEBUG] ✅ Option encontrado: id={option.id}, name={option.name}")
                    
                    # Intentar obtener el item_id del CRM
                    # Primero verificar si option o variant tienen crm_item_id
                    item_id = getattr(option, 'crm_item_id', None) or getattr(variant, 'crm_item_id', None)
                    
                    # Si no hay crm_item_id, usar crm_product_id del producto
                    if not item_id:
                        if product.crm_product_id:
                            item_id = product.crm_product_id
                            print(f"[DEBUG] ⚠️  No se encontró crm_item_id, usando crm_product_id={item_id} del producto")
                        else:
                            print(f"[DEBUG] ❌ No se encontró crm_item_id ni crm_product_id para producto {product.name}")
                            items_without_crm_id.append(f"Producto {product.name}: sin crm_product_id ni crm_item_id")
                            continue
                    
                    quantity = item.get('quantity', 1)
                    price = float(item.get('price', 0))
                    
                    print(f"[DEBUG] ✅ Item mapeado: item_id={item_id}, quantity={quantity}, price={price}")
                    
                    js_items.append({
                        "id": None,
                        "accion": "N",
                        "item_id": item_id,
                        "cantidad_recibida": quantity,
                        "precio": price,
                        "unitario_sin_fpago": price,
                        "descripcion": product.name
                    })
                
                if not js_items:
                    error_msg = 'No se pudieron mapear los productos al CRM. '
                    if items_without_crm_id:
                        error_msg += 'Productos sin mapeo: ' + ', '.join(items_without_crm_id)
                    else:
                        error_msg += 'Verifique que los productos tengan crm_product_id o crm_item_id'
                    return jsonify({
                        'success': False,
                        'error': error_msg
                    }), 400
                
                print(f"[DEBUG] ✅ Total de items mapeados: {len(js_items)}/{len(items)}")
                
                # Preparar payload para crear_venta
                fecha_detalle = datetime.now().strftime('%Y-%m-%d')
                
                # Debug del teléfono antes de crear el payload
                phone_final = phone or ""
                print(f"[DEBUG] Teléfono final antes de payload: '{phone_final}'")
                print(f"[DEBUG] Teléfono final - Type: {type(phone_final)}")
                print(f"[DEBUG] Teléfono final - Length: {len(phone_final)}")
                print(f"[DEBUG] Teléfono final - Is empty: {not phone_final}")
                if phone_final:
                    print(f"[DEBUG] Teléfono final - Contains spaces: {' ' in phone_final}")
                    print(f"[DEBUG] Teléfono final - Contains dashes: {'-' in phone_final}")
                    print(f"[DEBUG] Teléfono final - Contains parentheses: {'(' in phone_final or ')' in phone_final}")
                    print(f"[DEBUG] Teléfono final - Stripped: '{phone_final.strip()}'")
                
                venta_payload = {
                    "fecha_detalle": fecha_detalle,
                    "tipo_venta": crm_sale_type_id,
                    "cliente_nombre": f"{first_name} {last_name}".strip() or "Cliente",
                    "cliente_direccion": cliente_direccion or "",
                    "cliente_direccion_barrio": cliente_direccion_barrio or "",
                    "cliente_direccion_mas_datos": cliente_direccion_mas_datos,
                    "tipo_documento_cliente": crm_doc_type_id_int,
                    "documento_cliente": formatted_document or "",
                    "cliente_telefono": phone_final or "",
                    "cel_alternativo": alternate_phone if alternate_phone else None,
                    "email_cliente": email or "",
                    "provincia_id": crm_province_id,
                    "localidad": city or "",
                    "zona_id": crm_zone_id,
                    "observaciones": data.get('observations', ''),
                    "lat_long": {"latitud": 0.0, "longitud": 0.0},  # Por ahora 0,0
                    "js": js_items,
                    "formaPagos": [
                        {
                            "medios_pago_id": 1,  # Abonar al recibir
                            "monto_total": total,
                            "procesado": False
                        }
                    ]
                }
                
                # Debug del payload completo
                print(f"[DEBUG] Payload completo para crear_venta: {json.dumps(venta_payload, indent=2, default=str)}")
                
                # Llamar directamente a la función crear_venta usando el contexto de request de Flask
                from flask import current_app
                from routes.public_api import crear_venta
                
                # Crear un contexto de request temporal para simular la llamada
                with current_app.test_request_context(
                    '/api/ventas/crear',
                    method='POST',
                    json=venta_payload,
                    headers={'Authorization': f'Bearer {Config.API_KEY}'}
                ):
                    # Llamar directamente a la función
                    response = crear_venta()
                    
                    # Manejar si la respuesta es una tupla (response, status_code)
                    if isinstance(response, tuple):
                        response_obj, status_code = response
                    else:
                        response_obj = response
                        status_code = response_obj.status_code if hasattr(response_obj, 'status_code') else 200
                    
                    # Extraer los datos de la respuesta
                    if hasattr(response_obj, 'get_json'):
                        response_data = response_obj.get_json()
                    elif hasattr(response_obj, 'data'):
                        # Si es un Response object, obtener el JSON
                        response_data = json.loads(response_obj.data.decode('utf-8'))
                    else:
                        # Si es un dict directamente
                        response_data = response_obj if isinstance(response_obj, dict) else {}
                    
                    # Verificar el status code
                    if status_code != 200:
                        error_msg = response_data.get("message", "Error desconocido")
                        # Si hay errores específicos, agregarlos al mensaje
                        if "errors" in response_data:
                            errors = response_data.get("errors", {})
                            error_details = []
                            for field, field_errors in errors.items():
                                if isinstance(field_errors, list):
                                    error_details.extend([f"{field}: {e}" for e in field_errors])
                                else:
                                    error_details.append(f"{field}: {field_errors}")
                            if error_details:
                                error_msg += " - " + ", ".join(error_details)
                        
                        return jsonify({
                            'success': False,
                            'error': f'Error al crear venta en CRM: {error_msg}'
                        }), status_code
                    
                    if not response_data.get('status', False):
                        return jsonify({
                            'success': False,
                            'error': f'Error al crear venta en CRM: {response_data.get("message", "Error desconocido")}'
                        }), 500
                    
                    # Obtener el crm_order_id de la respuesta
                    # El endpoint externo retorna venta_id en el root, pero crear_venta lo estructura en data.crm_order_id
                    crm_order_id = response_data.get('data', {}).get('crm_order_id') or response_data.get('venta_id') or response_data.get('data', {}).get('venta_id')
                    print(f"[DEBUG] crm_order_id extraído de la respuesta: {crm_order_id}")
                    print(f"[DEBUG] Respuesta completa de crear_venta: {json.dumps(response_data, indent=2, default=str)}")
                    
                    # Forzar flush de la sesión para asegurar que los cambios se vean
                    try:
                        db.session.flush()
                    except:
                        pass
                    
                    # Verificar que crear_venta guardó los datos en crm_orders
                    # Hacer esto después de que el contexto de test_request_context termine
                    if crm_order_id:
                        print(f"[DEBUG] Verificando datos en crm_orders para crm_order_id={crm_order_id}")
                
            except Exception as e:
                import traceback
                print(f"Error al crear venta en CRM: {str(e)}")
                print(traceback.format_exc())
                return jsonify({
                    'success': False,
                    'error': f'Error al crear venta en CRM: {str(e)}'
                }), 500
        
        # Verificar que crear_venta guardó los datos en crm_orders (después de que termine el contexto test_request_context)
        if crm_order_id:
            try:
                # Hacer un refresh de la sesión para ver los cambios
                db.session.expire_all()
                check_crm_order = text("""
                    SELECT client_name, client_email, client_address, client_phone, 
                           crm_zone_id, crm_province_id, city, total_sale, crm_sale_type_id,
                           client_document, crm_doc_type_id, receipt_number
                    FROM crm_orders 
                    WHERE crm_order_id = :crm_order_id
                """)
                result_check = db.session.execute(check_crm_order, {'crm_order_id': crm_order_id})
                crm_order_row = result_check.fetchone()
                if crm_order_row:
                    print(f"[DEBUG] ✅ Datos en crm_orders: client_name={crm_order_row[0]}, client_email={crm_order_row[1]}, client_address={crm_order_row[2]}, client_phone={crm_order_row[3]}, crm_zone_id={crm_order_row[4]}, crm_province_id={crm_order_row[5]}, city={crm_order_row[6]}, total_sale={crm_order_row[7]}, crm_sale_type_id={crm_order_row[8]}, client_document={crm_order_row[9]}, crm_doc_type_id={crm_order_row[10]}, receipt_number={crm_order_row[11]}")
                else:
                    print(f"[DEBUG] ⚠️ No se encontró registro en crm_orders con crm_order_id={crm_order_id}")
            except Exception as check_error:
                print(f"[DEBUG] Error al verificar crm_orders: {str(check_error)}")
                import traceback
                print(traceback.format_exc())
        
        # Verificar si ya existe una orden con este crm_order_id
        existing_order = None
        if crm_order_id:
            existing_order = Order.query.filter_by(crm_order_id=crm_order_id).first()
            if existing_order:
                print(f"[DEBUG] Orden existente encontrada con crm_order_id={crm_order_id}, actualizando campos...")
                # Actualizar los campos de la orden existente
                existing_order.user_id = user.id
                existing_order.total = total
                existing_order.payment_method = data.get('payment_method', 'card')
                existing_order.payment_processed = not pay_on_delivery
                existing_order.crm_sale_type_id = crm_sale_type_id if pay_on_delivery else None
                
                # Actualizar used_wallet_amount
                used_wallet_amount = None
                if data.get('used_wallet_amount'):
                    used_wallet_amount = float(data.get('used_wallet_amount'))
                elif data.get('wallet_amount'):
                    used_wallet_amount = float(data.get('wallet_amount'))
                elif data.get('use_wallet_balance') and data.get('wallet_amount'):
                    used_wallet_amount = float(data.get('wallet_amount'))
                existing_order.used_wallet_amount = used_wallet_amount
                
                try:
                    db.session.commit()
                    # Refrescar el objeto para asegurar que los cambios se persistan
                    db.session.refresh(existing_order)
                    print(f"[DEBUG] Orden existente actualizada exitosamente")
                    print(f"[DEBUG] Verificación post-commit - user_id={existing_order.user_id}, total={existing_order.total}, payment_method={existing_order.payment_method}, payment_processed={existing_order.payment_processed}, crm_sale_type_id={existing_order.crm_sale_type_id}, used_wallet_amount={existing_order.used_wallet_amount}")
                    order_dict = existing_order.to_dict()
                    print(f"[DEBUG] Orden dict después de refresh: {json.dumps(order_dict, indent=2, default=str)}")
                    return jsonify({
                        'success': True,
                        'data': order_dict,
                        'message': 'Orden actualizada exitosamente'
                    }), 200
                except Exception as e:
                    db.session.rollback()
                    print(f"[DEBUG] Error al actualizar orden existente: {str(e)}")
                    raise
        
        # Obtener used_wallet_amount (puede venir como wallet_amount o used_wallet_amount)
        used_wallet_amount = None
        if data.get('used_wallet_amount'):
            used_wallet_amount = float(data.get('used_wallet_amount'))
        elif data.get('wallet_amount'):
            used_wallet_amount = float(data.get('wallet_amount'))
        elif data.get('use_wallet_balance') and data.get('wallet_amount'):
            used_wallet_amount = float(data.get('wallet_amount'))
        
        # Crear la orden en la tabla orders
        order = Order(
            user_id=user.id,
            crm_order_id=crm_order_id,
            crm_sale_type_id=crm_sale_type_id if pay_on_delivery else None,
            total=total,
            status='pending',
            payment_method=data.get('payment_method', 'card'),
            payment_processed=not pay_on_delivery,  # False si es "abonar al recibir", True si ya se pagó
            used_wallet_amount=used_wallet_amount
        )
        
        print(f"[DEBUG] Creando orden: user_id={user.id}, total={total}, payment_method={data.get('payment_method')}, used_wallet_amount={used_wallet_amount}, crm_sale_type_id={crm_sale_type_id if pay_on_delivery else None}")
        
        try:
            db.session.add(order)
            db.session.commit()
            # Refrescar el objeto para asegurar que los cambios se persistan
            db.session.refresh(order)
            print(f"[DEBUG] Orden creada exitosamente - user_id={order.user_id}, total={order.total}, payment_method={order.payment_method}, payment_processed={order.payment_processed}, crm_sale_type_id={order.crm_sale_type_id}, used_wallet_amount={order.used_wallet_amount}")
            
            # Enviar email de confirmación de compra
            try:
                from utils.email_service import email_service
                
                # Obtener receipt_number desde crm_orders si existe
                order_number = None
                if order.crm_order_id:
                    try:
                        receipt_query = text("""
                            SELECT receipt_number 
                            FROM crm_orders 
                            WHERE crm_order_id = :crm_order_id
                        """)
                        receipt_result = db.session.execute(receipt_query, {
                            'crm_order_id': order.crm_order_id
                        })
                        receipt_row = receipt_result.fetchone()
                        if receipt_row and receipt_row[0]:
                            order_number = receipt_row[0]
                    except Exception as receipt_error:
                        print(f"[DEBUG] Error al obtener receipt_number: {str(receipt_error)}")
                
                # Si no se encontró receipt_number, usar valor por defecto
                if not order_number:
                    order_number = f"ORD-{order.created_at.strftime('%Y')}-{str(order.id)[:8].upper()}"
                
                # Obtener información del usuario
                user_email = user.email
                user_first_name = user.first_name or 'Cliente'
                
                # Formatear el total
                order_total = f"${float(order.total):,.0f}".replace(',', '.')
                
                # Construir URL del pedido (opcional)
                frontend_url = Config.FRONTEND_URL if hasattr(Config, 'FRONTEND_URL') else os.getenv('FRONTEND_URL', 'https://bausing.com.ar')
                order_url = f"{frontend_url.rstrip('/')}/usuario?order={order.id}"
                
                # Enviar email
                email_sent = email_service.send_order_confirmation_email(
                    user_email=user_email,
                    user_first_name=user_first_name,
                    order_number=order_number,
                    order_total=order_total,
                    order_url=order_url
                )
                
                if email_sent:
                    print(f"[DEBUG] ✅ Email de confirmación enviado a {user_email} para orden {order_number}")
                else:
                    print(f"[DEBUG] ⚠️ No se pudo enviar email de confirmación a {user_email}")
                    
            except Exception as email_error:
                # No fallar la creación de la orden si falla el envío del email
                import traceback
                print(f"[DEBUG] ❌ Error al enviar email de confirmación: {str(email_error)}")
                print(traceback.format_exc())
                
        except IntegrityError as e:
            db.session.rollback()
            # Si hay un error de integridad (duplicado), buscar la orden existente
            if crm_order_id:
                existing_order = Order.query.filter_by(crm_order_id=crm_order_id).first()
                if existing_order:
                    # Actualizar los campos de la orden existente
                    existing_order.user_id = user.id
                    existing_order.total = total
                    existing_order.payment_method = data.get('payment_method', 'card')
                    existing_order.payment_processed = not pay_on_delivery
                    existing_order.crm_sale_type_id = crm_sale_type_id if pay_on_delivery else None
                    existing_order.used_wallet_amount = used_wallet_amount
                    try:
                        db.session.commit()
                        db.session.refresh(existing_order)
                        print(f"[DEBUG] Orden duplicada actualizada - user_id={existing_order.user_id}, total={existing_order.total}, payment_method={existing_order.payment_method}")
                        
                        # Enviar email de confirmación de compra (solo si no se había enviado antes)
                        try:
                            from utils.email_service import email_service
                            
                            # Obtener receipt_number desde crm_orders si existe
                            order_number = None
                            if existing_order.crm_order_id:
                                try:
                                    receipt_query = text("""
                                        SELECT receipt_number 
                                        FROM crm_orders 
                                        WHERE crm_order_id = :crm_order_id
                                    """)
                                    receipt_result = db.session.execute(receipt_query, {
                                        'crm_order_id': existing_order.crm_order_id
                                    })
                                    receipt_row = receipt_result.fetchone()
                                    if receipt_row and receipt_row[0]:
                                        order_number = receipt_row[0]
                                except Exception as receipt_error:
                                    print(f"[DEBUG] Error al obtener receipt_number: {str(receipt_error)}")
                            
                            # Si no se encontró receipt_number, usar valor por defecto
                            if not order_number:
                                order_number = f"ORD-{existing_order.created_at.strftime('%Y')}-{str(existing_order.id)[:8].upper()}"
                            
                            # Obtener información del usuario
                            user_email = user.email
                            user_first_name = user.first_name or 'Cliente'
                            
                            # Formatear el total
                            order_total = f"${float(existing_order.total):,.0f}".replace(',', '.')
                            
                            # Construir URL del pedido (opcional)
                            frontend_url = Config.FRONTEND_URL if hasattr(Config, 'FRONTEND_URL') else os.getenv('FRONTEND_URL', 'https://bausing.com.ar')
                            order_url = f"{frontend_url.rstrip('/')}/usuario?order={existing_order.id}"
                            
                            # Enviar email
                            email_sent = email_service.send_order_confirmation_email(
                                user_email=user_email,
                                user_first_name=user_first_name,
                                order_number=order_number,
                                order_total=order_total,
                                order_url=order_url
                            )
                            
                            if email_sent:
                                print(f"[DEBUG] ✅ Email de confirmación enviado a {user_email} para orden {order_number}")
                            else:
                                print(f"[DEBUG] ⚠️ No se pudo enviar email de confirmación a {user_email}")
                                
                        except Exception as email_error:
                            # No fallar la actualización de la orden si falla el envío del email
                            import traceback
                            print(f"[DEBUG] ❌ Error al enviar email de confirmación: {str(email_error)}")
                            print(traceback.format_exc())
                        
                        return jsonify({
                            'success': True,
                            'data': existing_order.to_dict(),
                            'message': 'Orden ya existe (duplicada)'
                        }), 200
                    except Exception as update_error:
                        db.session.rollback()
                        print(f"[DEBUG] Error al actualizar orden duplicada: {str(update_error)}")
                        raise
            # Si no se encontró la orden existente, re-lanzar el error
            raise
        
        order_dict = order.to_dict()
        print(f"[DEBUG] Orden creada exitosamente: {json.dumps(order_dict, indent=2, default=str)}")
        
        # Si es pago con tarjeta sin "abonar al recibir", procesar pago con MercadoPago Checkout API (vía Payments)
        response_data = {
            'success': True,
            'data': order_dict,
            'message': 'Orden creada exitosamente'
        }
        
        # Obtener payment_method de los datos
        payment_method = data.get('payment_method', 'card')
        
        if payment_method == 'card' and not pay_on_delivery:
            mp_token = data.get('mercadopago_token')
            mp_installments = data.get('mercadopago_installments', 1)
            mp_payment_method_id = data.get('mercadopago_payment_method_id')
            mp_issuer_id = data.get('mercadopago_issuer_id')
            
            print(f"[DEBUG] Token recibido: {mp_token[:20] if mp_token and len(mp_token) > 20 else mp_token}... (longitud: {len(mp_token) if mp_token else 0})")
            print(f"[DEBUG] Installments: {mp_installments}")
            print(f"[DEBUG] Payment Method ID: {mp_payment_method_id}")
            print(f"[DEBUG] Issuer ID: {mp_issuer_id}")
            
            if not mp_token:
                return jsonify({
                    'success': False,
                    'error': 'Token de tarjeta de MercadoPago requerido'
                }), 400
            
            # Validar que el token tenga un formato válido (debe ser un string no vacío)
            if not isinstance(mp_token, str) or len(mp_token.strip()) == 0:
                return jsonify({
                    'success': False,
                    'error': 'Token de tarjeta inválido'
                }), 400
            
            if not mp_payment_method_id:
                return jsonify({
                    'success': False,
                    'error': 'Método de pago no identificado'
                }), 400
            
            try:
                # El token ya fue verificado antes de crear la orden, pero lo verificamos de nuevo por seguridad
                mp_access_token = Config.MP_ACCESS_TOKEN or os.getenv('MP_ACCESS_TOKEN')
                if not mp_access_token:
                    print("[DEBUG] ⚠️ MP_ACCESS_TOKEN no configurado - esto no debería pasar")
                    # Esto no debería pasar porque ya lo verificamos antes, pero por seguridad:
                    order.payment_processed = False
                    order.status = 'pending'
                    db.session.commit()
                    
                    return jsonify({
                        'success': False,
                        'error': 'Configuración de pago no disponible. La orden se creó pero el pago no pudo ser procesado. Por favor, contacta al soporte.',
                        'order_id': str(order.id)
                    }), 500
                
                # Calcular el total a pagar (descontando wallet si aplica)
                total_to_pay = float(total)
                if used_wallet_amount:
                    total_to_pay = max(0, total_to_pay - float(used_wallet_amount))
                
                # Obtener DNI del cliente
                customer_dni = formData.get('dni', '') if formData else ''
                if not customer_dni:
                    customer_dni = address_data.get('dni', '')
                
                # Procesar pago con MercadoPago Checkout API (vía Payments) - Core Methods
                # Limpiar el token (eliminar espacios en blanco)
                mp_token_clean = mp_token.strip()
                
                print(f"[DEBUG] Token limpio a usar: {mp_token_clean[:20]}... (longitud: {len(mp_token_clean)})")
                print(f"[DEBUG] Total a pagar: {total_to_pay}")
                
                # Construir el objeto payer con toda la información disponible
                payer_data = {
                    "email": user.email or formData.get('email', '')
                }
                
                # Agregar identificación solo si tenemos DNI
                if customer_dni:
                    payer_data["identification"] = {
                        "type": "DNI",
                        "number": str(customer_dni)
                    }
                
                # Agregar nombre completo si está disponible
                first_name = formData.get('first_name', '') if formData else ''
                last_name = formData.get('last_name', '') if formData else ''
                if first_name or last_name:
                    payer_data["first_name"] = first_name
                    payer_data["last_name"] = last_name
                
                payment_payload = {
                    "token": mp_token_clean,
                    "installments": int(mp_installments),
                    "transaction_amount": float(total_to_pay),
                    "description": f"Orden {str(order.id)[:8]}",
                    "payment_method_id": mp_payment_method_id,
                    "payer": payer_data,
                    "external_reference": str(order.id),
                    "statement_descriptor": "BAUSING"
                }
                
                # Agregar notification_url solo si BACKEND_URL está configurado y es válido
                backend_url = Config.BACKEND_URL or os.getenv('BACKEND_URL', 'http://localhost:5000')
                
                # Construir la URL del webhook
                notification_url = f"{backend_url.rstrip('/')}/api/orders/webhooks/mercadopago"
                
                # Validar que la URL sea válida (debe empezar con http:// o https://)
                if notification_url.startswith(('http://', 'https://')):
                    # En desarrollo, localhost puede funcionar, pero MercadoPago puede rechazarlo
                    # En producción, debe ser una URL pública accesible
                    if 'localhost' in notification_url:
                        print(f"[DEBUG] ⚠️ notification_url es localhost: {notification_url}")
                        print("[DEBUG] ⚠️ MercadoPago puede rechazar localhost. Omitiendo notification_url.")
                        # No agregar notification_url si es localhost
                    else:
                        payment_payload["notification_url"] = notification_url
                        print(f"[DEBUG] ✅ notification_url configurada: {notification_url}")
                else:
                    print(f"[DEBUG] ⚠️ notification_url no es válida: {notification_url}")
                
                # Agregar issuer_id si está disponible
                if mp_issuer_id:
                    payment_payload["issuer_id"] = int(mp_issuer_id)
                
                # Generar idempotency key único para este pago (usar el ID de la orden)
                idempotency_key = str(order.id)
                
                # Log del payload completo (sin mostrar el token completo por seguridad)
                payload_log = payment_payload.copy()
                if 'token' in payload_log:
                    payload_log['token'] = f"{payload_log['token'][:20]}... (oculto)"
                print(f"[DEBUG] Payload completo a enviar a MercadoPago: {json.dumps(payload_log, indent=2, default=str)}")
                
                mp_response = requests.post(
                    "https://api.mercadopago.com/v1/payments",
                    headers={
                        "Authorization": f"Bearer {mp_access_token}",
                        "Content-Type": "application/json",
                        "X-Idempotency-Key": idempotency_key
                    },
                    json=payment_payload,
                    timeout=30
                )
                
                print(f"[DEBUG] Respuesta de MercadoPago: Status {mp_response.status_code}")
                if mp_response.status_code != 201:
                    print(f"[DEBUG] Respuesta completa: {mp_response.text}")
                
                if mp_response.status_code == 201:
                    mp_payment = mp_response.json()
                    payment_status = mp_payment.get('status')
                    payment_id = mp_payment.get('id')
                    
                    print(f"[DEBUG] ✅ Pago de MercadoPago procesado: {payment_id}, status: {payment_status}")
                    
                    # Obtener detalles adicionales del pago
                    status_detail = mp_payment.get('status_detail', '')
                    error_message_mp = mp_payment.get('error', {}).get('message', '') if mp_payment.get('error') else ''
                    
                    # Si el pago está aprobado, marcar la orden como pagada
                    if payment_status == 'approved':
                        order.payment_processed = True
                        order.status = 'pending'
                        db.session.commit()
                        print(f"[DEBUG] ✅ Orden {order.id} marcada como pagada")
                    elif payment_status == 'pending':
                        # El pago está pendiente, se procesará vía webhook
                        print(f"[DEBUG] ⚠️ Pago pendiente, esperando webhook")
                    else:
                        # Pago rechazado o en otro estado
                        # Construir mensaje de error más descriptivo
                        error_msg = f'El pago fue {payment_status}'
                        if status_detail:
                            error_msg += f' ({status_detail})'
                        if error_message_mp:
                            error_msg += f': {error_message_mp}'
                        else:
                            error_msg += '. Por favor, intenta con otra tarjeta o verifica los datos de la tarjeta.'
                        
                        print(f"[DEBUG] ❌ Pago rechazado: {error_msg}")
                        print(f"[DEBUG] Detalles completos del pago: {json.dumps(mp_payment, indent=2, default=str)}")
                        
                        # Marcar la orden como no pagada
                        order.payment_processed = False
                        order.status = 'pending'
                        db.session.commit()
                        
                        return jsonify({
                            'success': False,
                            'error': error_msg,
                            'payment_status': payment_status,
                            'payment_id': payment_id,
                            'status_detail': status_detail
                        }), 400
                    
                    response_data['payment'] = {
                        'id': payment_id,
                        'status': payment_status
                    }
                else:
                    error_data = mp_response.json() if mp_response.text else {}
                    error_message = error_data.get('message', 'Error al procesar el pago')
                    print(f"[DEBUG] ❌ Error al procesar pago: {mp_response.status_code} - {error_message}")
                    return jsonify({
                        'success': False,
                        'error': error_message,
                        'details': error_data
                    }), 400
                    
            except Exception as mp_error:
                import traceback
                print(f"[DEBUG] ❌ Error al procesar pago de MercadoPago: {str(mp_error)}")
                print(traceback.format_exc())
                return jsonify({
                    'success': False,
                    'error': f'Error al procesar el pago: {str(mp_error)}'
                }), 500
        
        return jsonify(response_data), 201
        
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error al crear orden: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Error al crear orden: {str(e)}'
        }), 500


@orders_bp.route('/api/orders/webhooks/mercadopago', methods=['POST', 'GET'])
def mercadopago_webhook():
    """
    Webhook de MercadoPago para procesar notificaciones de pago.
    Compatible con query params (v1) y body JSON (v2).
    """
    try:
        # Obtener datos del webhook (compatible con v1 y v2)
        topic = request.args.get('topic') or request.args.get('type')
        payment_id = request.args.get('id')
        
        # Intentar obtener del body JSON (v2)
        try:
            body = request.get_json() or {}
        except Exception:
            body = {}
        
        topic = topic or body.get('type')
        payment_id = payment_id or (body.get('data') or {}).get('id')
        
        if not topic or not payment_id:
            print("[MP-WH] Webhook sin topic o payment_id, ignorando")
            return '', 200
        
        # Solo procesar notificaciones de payment
        if topic not in ('payment', 'mp_payment'):
            print(f"[MP-WH] Topic '{topic}' no es payment, ignorando")
            return '', 200
        
        # Obtener el pago de MercadoPago
        mp_access_token = Config.MP_ACCESS_TOKEN or os.getenv('MP_ACCESS_TOKEN')
        if not mp_access_token:
            print("[MP-WH] ⚠️ MP_ACCESS_TOKEN no configurado")
            return '', 500
        
        mp_response = requests.get(
            f"https://api.mercadopago.com/v1/payments/{payment_id}",
            headers={"Authorization": f"Bearer {mp_access_token}"},
            timeout=30
        )
        
        if mp_response.status_code != 200:
            print(f"[MP-WH] ❌ Error al obtener pago {payment_id}: {mp_response.status_code}")
            return '', 400
        
        payment = mp_response.json()
        
        # Solo procesar pagos aprobados
        if payment.get('status') != 'approved':
            print(f"[MP-WH] Pago {payment_id} no está approved (status: {payment.get('status')}), ignorando")
            return '', 200
        
        # Obtener order_id desde external_reference
        external_reference = payment.get('external_reference') or (payment.get('metadata') or {}).get('order_id')
        if not external_reference:
            print(f"[MP-WH] ⚠️ Pago {payment_id} sin external_reference")
            return '', 200
        
        try:
            order_id = uuid.UUID(external_reference)
        except ValueError:
            print(f"[MP-WH] ⚠️ external_reference '{external_reference}' no es un UUID válido")
            return '', 200
        
        # Buscar la orden
        order = Order.query.get(order_id)
        if not order:
            print(f"[MP-WH] ⚠️ Orden {order_id} no encontrada")
            return '', 200
        
        # Si la orden ya está pagada, no hacer nada
        if order.payment_processed:
            print(f"[MP-WH] Orden {order_id} ya está pagada, ignorando")
            return '', 200
        
        # Marcar la orden como pagada
        try:
            order.payment_processed = True
            order.status = 'pending'  # Cambiar a 'pending' para que se procese
            db.session.commit()
            print(f"[MP-WH] ✅ Orden {order_id} marcada como pagada")
            
            # Aquí podrías agregar lógica adicional como:
            # - Descontar el wallet_amount si se usó
            # - Enviar email de confirmación
            # - Crear la venta en el CRM si es necesario
            
        except Exception as e:
            db.session.rollback()
            print(f"[MP-WH] ❌ Error al actualizar orden {order_id}: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return '', 500
        
        return '', 200
        
    except Exception as e:
        import traceback
        print(f"[MP-WH] ❌ Error en webhook: {str(e)}")
        print(traceback.format_exc())
        return '', 500
