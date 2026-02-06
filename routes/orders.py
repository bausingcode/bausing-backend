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
from datetime import datetime, timezone, timedelta
import re
import json
import os
import requests

orders_bp = Blueprint('orders', __name__)

# Función helper para obtener la hora de Argentina (UTC-3)
def get_argentina_time():
    """Retorna la fecha y hora actual en zona horaria de Argentina (UTC-3) como datetime naive"""
    argentina_tz = timezone(timedelta(hours=-3))
    return datetime.now(argentina_tz).replace(tzinfo=None)

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

def create_crm_order_from_order(order):
    """
    Crea una orden en el CRM a partir de una orden existente.
    Retorna el crm_order_id si se crea exitosamente, None si hay error.
    """
    try:
        if order.crm_order_id:
            print(f"[DEBUG] Orden {order.id} ya tiene crm_order_id={order.crm_order_id}, saltando creación")
            return order.crm_order_id
        
        print(f"[DEBUG] Creando orden en CRM para orden {order.id}...")
        
        from models.order_item import OrderItem
        from models.product import Product, ProductVariant, ProductVariantOption
        from models.address import Address
        from models.user import User
        from models.doc_type import DocType
        from datetime import datetime
        from flask import current_app
        from routes.public_api import crear_venta
        
        # Obtener usuario y dirección
        user = User.query.get(order.user_id)
        if not user:
            print(f"[DEBUG] ⚠️ Usuario {order.user_id} no encontrado")
            return None
        
        # Obtener dirección de entrega
        address = Address.query.filter_by(user_id=user.id, is_default=True).first()
        if not address:
            address = Address.query.filter_by(user_id=user.id).first()
        
        if not address:
            print(f"[DEBUG] ⚠️ No se encontró dirección para usuario {user.id}")
            return None
        
        # Obtener items de la orden
        order_items = OrderItem.query.filter_by(order_id=order.id).all()
        if not order_items:
            print(f"[DEBUG] ⚠️ Orden {order.id} no tiene items")
            return None
        
        # Obtener datos del cliente
        first_name = user.first_name or ''
        last_name = user.last_name or ''
        email = user.email or ''
        phone = user.phone or address.phone or ''
        
        # Obtener tipo de documento del usuario (usar DNI por defecto si no está configurado)
        doc_type = DocType.query.filter_by(code='DNI').first()
        if not doc_type:
            # Si no existe DNI, usar el primero disponible
            doc_type = DocType.query.first()
        
        if not doc_type:
            print(f"[DEBUG] ⚠️ No se encontró ningún tipo de documento en la base de datos")
            return None
        
        # Obtener crm_doc_type_id
        crm_doc_type_id_int = get_crm_doc_type_id_from_doc_type(str(doc_type.id))
        if not crm_doc_type_id_int:
            doc_type_name_lower = doc_type.name.lower() if doc_type.name else ""
            if 'cuit' in doc_type_name_lower or 'cuil' in doc_type_name_lower:
                crm_doc_type_id_int = 2
            else:
                crm_doc_type_id_int = 1  # DNI por defecto
        
        # Obtener provincia y zona
        crm_province_id = get_crm_province_id_from_province(address.province_id)
        if not crm_province_id:
            print(f"[DEBUG] ⚠️ No se pudo obtener crm_province_id")
            return None
        
        crm_zone_id = get_crm_zone_id_from_locality(address.city)
        if not crm_zone_id:
            print(f"[DEBUG] ⚠️ No se pudo obtener crm_zone_id")
            return None
        
        # Preparar items para el CRM
        js_items = []
        for order_item in order_items:
            product = Product.query.get(order_item.product_id)
            if not product:
                continue
            
            variant = ProductVariant.query.filter_by(product_id=product.id).first()
            if not variant:
                continue
            
            option = ProductVariantOption.query.filter_by(product_variant_id=variant.id).first()
            if not option:
                continue
            
            item_id = getattr(option, 'crm_item_id', None) or getattr(variant, 'crm_item_id', None)
            if not item_id and product.crm_product_id:
                item_id = product.crm_product_id
            
            if not item_id:
                continue
            
            # Calcular precio total (precio unitario * cantidad)
            # order_item.unit_price es el precio unitario
            cantidad = order_item.quantity
            precio_unitario = float(order_item.unit_price)
            
            precio_total = precio_unitario * cantidad
            
            js_items.append({
                "id": None,
                "accion": "N",
                "item_id": item_id,
                "cantidad_recibida": cantidad,
                "precio": precio_total,  # Precio TOTAL según documentación del endpoint externo
                "unitario_sin_fpago": precio_unitario,  # Precio unitario
                "descripcion": product.name
            })
        
        if not js_items:
            print(f"[DEBUG] ⚠️ No se pudieron mapear items al CRM")
            return None
        
        # Preparar payload para crear_venta
        fecha_detalle = get_argentina_time().strftime('%Y-%m-%d')
        crm_sale_type_id = order.crm_sale_type_id or 1
        
        # Formatear documento
        formatted_document = format_document_number(str(doc_type.id), user.dni or '', crm_sale_type_id)
        
        # Construir dirección
        cliente_direccion = f"{address.street} {address.number}".strip()
        cliente_direccion_barrio = address.city or ""
        cliente_direccion_mas_datos = address.additional_info or None
        
        # Normalizar teléfono
        def normalize_phone(phone_str):
            if not phone_str:
                return "3510000000"
            phone_str = str(phone_str).strip()
            phone_cleaned = ''.join(c for c in phone_str if c.isdigit())
            if phone_cleaned.startswith('0'):
                phone_cleaned = phone_cleaned[1:]
            if len(phone_cleaned) < 8 or len(phone_cleaned) > 11:
                return "3510000000"
            return phone_cleaned
        
        phone_final = normalize_phone(phone)
        
        # Determinar medio de pago según payment_method
        medios_pago_id = 2 if order.payment_method == 'card' else 1  # 2 = Tarjeta, 1 = Abonar al recibir
        
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
            "cel_alternativo": None,
            "email_cliente": email or "",
            "provincia_id": crm_province_id,
            "localidad": address.city or "",
            "zona_id": crm_zone_id,
            "observaciones": "",
            "lat_long": {"latitud": 0.0, "longitud": 0.0},
            "js": js_items,
            "formaPagos": [
                {
                    "medios_pago_id": medios_pago_id,
                    "monto_total": float(order.total),
                    "procesado": order.payment_processed  # True si ya se pagó, False si es "abonar al recibir"
                }
            ]
        }
        
        # Llamar a crear_venta usando /api/ventas/crear
        with current_app.test_request_context(
            '/api/ventas/crear',
            method='POST',
            json=venta_payload,
            headers={'Authorization': f'Bearer {Config.API_KEY}'}
        ):
            response = crear_venta()
            
            if isinstance(response, tuple):
                response_obj, status_code = response
            else:
                response_obj = response
                status_code = response_obj.status_code if hasattr(response_obj, 'status_code') else 200
            
            if hasattr(response_obj, 'get_json'):
                response_data = response_obj.get_json()
            elif hasattr(response_obj, 'data'):
                response_data = json.loads(response_obj.data.decode('utf-8'))
            else:
                response_data = response_obj if isinstance(response_obj, dict) else {}
            
            if status_code == 200 and response_data.get('status', False):
                crm_order_id = response_data.get('data', {}).get('crm_order_id') or response_data.get('venta_id')
                if crm_order_id:
                    order.crm_order_id = crm_order_id
                    db.session.commit()
                    print(f"[DEBUG] ✅ Orden {order.id} creada en CRM con crm_order_id={crm_order_id}")
                    return crm_order_id
                else:
                    print(f"[DEBUG] ⚠️ No se pudo obtener crm_order_id de la respuesta")
                    return None
            else:
                print(f"[DEBUG] ⚠️ Error al crear venta en CRM: {response_data.get('message', 'Error desconocido')}")
                return None
                
    except Exception as crm_error:
        import traceback
        print(f"[DEBUG] ⚠️ Error al crear venta en CRM: {str(crm_error)}")
        print(traceback.format_exc())
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
        
        # Optimización: Cargar datos de forma batch para mejorar rendimiento
        order_ids = [order.id for order in orders]
        user_ids = list(set([order.user_id for order in orders]))
        crm_order_ids = [order.crm_order_id for order in orders if hasattr(order, 'crm_order_id') and order.crm_order_id]
        
        # Cargar direcciones de todos los usuarios en una sola query
        addresses_map = {}
        if user_ids:
            addresses = Address.query.filter(Address.user_id.in_(user_ids)).all()
            for address in addresses:
                if address.user_id not in addresses_map:
                    addresses_map[address.user_id] = address.to_dict()
        
        # Cargar receipt_numbers de todas las órdenes en una sola query
        receipt_numbers_map = {}
        if crm_order_ids:
            try:
                # Usar IN para PostgreSQL
                placeholders = ','.join([f':id_{i}' for i in range(len(crm_order_ids))])
                receipt_query = text(f"""
                    SELECT crm_order_id, receipt_number 
                    FROM crm_orders 
                    WHERE crm_order_id IN ({placeholders})
                """)
                params = {f'id_{i}': crm_id for i, crm_id in enumerate(crm_order_ids)}
                receipt_result = db.session.execute(receipt_query, params)
                for row in receipt_result:
                    if row[1]:  # receipt_number
                        receipt_numbers_map[row[0]] = row[1]
            except Exception as e:
                print(f"[DEBUG] Error al cargar receipt_numbers: {str(e)}")
                pass
        
        # Cargar items de todas las órdenes en una sola query
        items_map = {}
        if order_ids:
            try:
                from models.order_item import OrderItem
                order_items = OrderItem.query.filter(OrderItem.order_id.in_(order_ids)).all()
                
                # Cargar todos los productos de una vez
                product_ids = list(set([item.product_id for item in order_items]))
                products_map = {}
                if product_ids:
                    products = Product.query.filter(Product.id.in_(product_ids)).all()
                    products_map = {p.id: p for p in products}
                
                # Cargar todas las variantes de una vez
                variants_map = {}
                variant_ids = []
                if product_ids:
                    variants = ProductVariant.query.filter(ProductVariant.product_id.in_(product_ids)).all()
                    for variant in variants:
                        if variant.product_id not in variants_map:
                            variants_map[variant.product_id] = variant
                        variant_ids.append(variant.id)
                
                # Cargar todas las opciones de una vez
                options_map = {}
                if variant_ids:
                    options = ProductVariantOption.query.filter(ProductVariantOption.product_variant_id.in_(variant_ids)).all()
                    for option in options:
                        if option.product_variant_id not in options_map:
                            options_map[option.product_variant_id] = option
                
                # Procesar items con datos pre-cargados
                for item in order_items:
                    if item.order_id not in items_map:
                        items_map[item.order_id] = []
                    
                    # Obtener información del producto desde el mapa
                    product = products_map.get(item.product_id)
                    product_name = product.name if product else "Producto"
                    product_image = None
                    if product:
                        # Intentar obtener imagen del producto desde datos pre-cargados
                        variant = variants_map.get(product.id)
                        if variant:
                            option = options_map.get(variant.id)
                            if option and hasattr(option, 'image_url') and option.image_url:
                                product_image = option.image_url
                            elif hasattr(variant, 'image_url') and variant.image_url:
                                product_image = variant.image_url
                        if not product_image and hasattr(product, 'image_url') and product.image_url:
                            product_image = product.image_url
                    
                    items_map[item.order_id].append({
                        'id': str(item.id),
                        'product_id': str(item.product_id),
                        'product_name': product_name,
                        'product_image': product_image,
                        'quantity': item.quantity,
                        'unit_price': float(item.unit_price) if item.unit_price else 0.0,
                        'total_price': float(item.unit_price * item.quantity) if item.unit_price else 0.0,
                    })
            except Exception as e:
                print(f"[DEBUG] Error al cargar items: {str(e)}")
                import traceback
                traceback.print_exc()
                # Si falla, items_map quedará vacío y se usarán arrays vacíos
        
        # Convertir órdenes a formato esperado por el frontend usando datos pre-cargados
        orders_data = []
        for order in orders:
            order_dict = order_to_dict_optimized(
                order, 
                addresses_map.get(order.user_id),
                receipt_numbers_map.get(order.crm_order_id) if hasattr(order, 'crm_order_id') and order.crm_order_id else None,
                items_map.get(order.id, [])
            )
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
    Acepta UUID de orders o crm_order_id (número)
    """
    try:
        user = request.user
        
        # Intentar primero como UUID
        order = None
        try:
            order_uuid = uuid.UUID(order_id)
            order = Order.query.filter_by(id=order_uuid, user_id=user.id).first()
        except ValueError:
            # Si no es UUID, intentar como crm_order_id (número)
            try:
                crm_order_id = int(order_id)
                order = Order.query.filter_by(crm_order_id=crm_order_id, user_id=user.id).first()
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'ID de orden inválido. Debe ser un UUID o un número (crm_order_id)'
                }), 400
        
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


def order_to_dict_optimized(order, shipping_address=None, receipt_number=None, items=None):
    """
    Versión optimizada de order_to_dict que acepta datos pre-cargados
    """
    # Determinar payment_status basado en el status de la orden
    payment_status = "pending"
    if order.status in ["in_transit", "pending_delivery", "delivered"]:
        payment_status = "paid"
    elif order.status == "cancelled":
        payment_status = "failed"
    
    # Determinar pay_on_delivery
    pay_on_delivery = (order.payment_method == "cash" or order.payment_method == "transfer") and payment_status == "pending"
    
    # Usar receipt_number pre-cargado o UUID de la orden
    order_number = receipt_number if receipt_number else str(order.id)
    
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
        'items': items or [],
        'tracking_number': None,  # Por ahora None, se puede agregar después
        'tracking_url': None,  # Por ahora None, se puede agregar después
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'updated_at': order.created_at.isoformat() if order.created_at else None  # Por ahora usamos created_at
    }

def order_to_dict(order):
    """
    Convierte una orden del modelo a el formato esperado por el frontend
    Versión no optimizada para uso individual (mantener compatibilidad)
    """
    from sqlalchemy import text
    
    # Obtener la dirección de envío (si existe)
    shipping_address = None
    address = Address.query.filter_by(user_id=order.user_id).first()
    if address:
        shipping_address = address.to_dict()
    
    # Obtener items de la orden
    items = []
    try:
        from models.order_item import OrderItem
        order_items = OrderItem.query.filter_by(order_id=order.id).all()
        for item in order_items:
            product = Product.query.get(item.product_id)
            product_name = product.name if product else "Producto"
            product_image = None
            if product:
                variant = ProductVariant.query.filter_by(product_id=product.id).first()
                if variant:
                    option = ProductVariantOption.query.filter_by(product_variant_id=variant.id).first()
                    if option and hasattr(option, 'image_url') and option.image_url:
                        product_image = option.image_url
                    elif hasattr(variant, 'image_url') and variant.image_url:
                        product_image = variant.image_url
                if not product_image and hasattr(product, 'image_url') and product.image_url:
                    product_image = product.image_url
            
            items.append({
                'id': str(item.id),
                'product_id': str(item.product_id),
                'product_name': product_name,
                'product_image': product_image,
                'quantity': item.quantity,
                'unit_price': float(item.unit_price) if item.unit_price else 0.0,
                'total_price': float(item.unit_price * item.quantity) if item.unit_price else 0.0,
            })
    except Exception:
        pass
    
    # Determinar payment_status basado en el status de la orden
    payment_status = "pending"
    if order.status in ["in_transit", "pending_delivery", "delivered"]:
        payment_status = "paid"
    elif order.status == "cancelled":
        payment_status = "failed"
    
    # Determinar pay_on_delivery
    pay_on_delivery = (order.payment_method == "cash" or order.payment_method == "transfer") and payment_status == "pending"
    
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
    
    # Si no se encontró receipt_number, usar UUID de la orden
    if not order_number:
        order_number = str(order.id)
    
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
        total = float(data['total'])  # Este total ya viene con el descuento de billetera aplicado desde el frontend
        formData = data.get('customer', {})  # Datos del cliente para el pago
        payment_method = data.get('payment_method', 'card')
        
        # Obtener used_wallet_amount (puede venir como wallet_amount o used_wallet_amount)
        # IMPORTANTE: Definir esto ANTES de cualquier validación que lo use
        used_wallet_amount = None
        if data.get('used_wallet_amount'):
            used_wallet_amount = float(data.get('used_wallet_amount'))
        elif data.get('wallet_amount'):
            used_wallet_amount = float(data.get('wallet_amount'))
        elif data.get('use_wallet_balance') and data.get('wallet_amount'):
            used_wallet_amount = float(data.get('wallet_amount'))
        
        # Si es pago con wallet completo y no se envió wallet_amount, usar el total original
        # Calcular el total original (antes del descuento) sumando los items
        if payment_method == 'wallet':
            if not used_wallet_amount or used_wallet_amount <= 0:
                # Si no se envió wallet_amount, calcular el total original desde los items
                total_original = sum(float(item.get('price', 0)) * item.get('quantity', 1) for item in items)
                if total_original > 0:
                    used_wallet_amount = total_original
                    print(f"[DEBUG] Método de pago wallet: usando total original como used_wallet_amount: {used_wallet_amount}")
                else:
                    return jsonify({
                        'success': False,
                        'error': 'Para pagar con billetera, debes tener saldo disponible'
                    }), 400
            
            # Si el total es mayor a 0 después del descuento, no se puede pagar completamente con wallet
            # (pero el total ya viene con el descuento aplicado, así que si es 0 está bien)
            if total > 0:
                # Si el total es mayor a 0, significa que el wallet no cubre todo
                # Pero espera, el total ya viene con el descuento aplicado desde el frontend
                # Si el método es wallet completo, el total debería ser 0
                # Si no es 0, significa que el wallet no cubre todo
                total_original_calc = sum(float(item.get('price', 0)) * item.get('quantity', 1) for item in items)
                if total_original_calc > used_wallet_amount:
                    return jsonify({
                        'success': False,
                        'error': f'El saldo de billetera no cubre el total. Total: ${total_original_calc:.2f}, Saldo disponible: ${used_wallet_amount:.2f}'
                    }), 400
        
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
        print(f"[DEBUG] used_wallet_amount calculado: {used_wallet_amount}")
        
        # Preparar datos para llamar a /api/ventas/crear
        # Primero necesitamos obtener los datos del usuario y dirección
        from models.address import Address
        from models.doc_type import DocType
        
        # Obtener dirección
        address = Address.query.filter_by(user_id=user.id, is_default=True).first()
        if not address:
            address = Address.query.filter_by(user_id=user.id).first()
        
        if not address:
            # Si no hay dirección guardada, usar la dirección del request
            address = Address(
                user_id=user.id,
                street=address_data.get('street', ''),
                number=address_data.get('number', ''),
                city=address_data.get('city', ''),
                province_id=uuid.UUID(address_data['province_id']) if isinstance(address_data.get('province_id'), str) else address_data.get('province_id'),
                phone=address_data.get('phone', ''),
                additional_info=address_data.get('additional_info', '')
            )
        
        # Obtener tipo de documento desde los datos del request o usar DNI por defecto
        doc_type_id = formData.get('document_type') or formData.get('doc_type_id')
        doc_type = None
        crm_doc_type_id_int = 1  # DNI por defecto
        
        if doc_type_id:
            try:
                doc_type_uuid = uuid.UUID(doc_type_id) if isinstance(doc_type_id, str) else doc_type_id
                doc_type = DocType.query.get(doc_type_uuid)
                if doc_type:
                    # Obtener crm_doc_type_id
                    crm_doc_type_id_int = get_crm_doc_type_id_from_doc_type(doc_type_id)
                    if not crm_doc_type_id_int:
                        doc_type_name_lower = doc_type.name.lower() if doc_type.name else ""
                        if 'cuit' in doc_type_name_lower or 'cuil' in doc_type_name_lower:
                            crm_doc_type_id_int = 2
                        else:
                            crm_doc_type_id_int = 1
            except Exception as e:
                print(f"[DEBUG] Error al obtener tipo de documento: {str(e)}")
                # Usar DNI por defecto si hay error
                crm_doc_type_id_int = 1
        
        # Si no hay doc_type pero necesitamos uno, usar DNI por defecto
        if not doc_type:
            doc_type = DocType.query.filter_by(code='DNI').first()
            if not doc_type:
                # Si no existe DNI, usar el primero disponible
                doc_type = DocType.query.first()
        
        if not doc_type:
            return jsonify({
                'success': False,
                'error': 'No se pudo determinar el tipo de documento'
            }), 400
        
        # Obtener provincia y zona
        province_id = address_data.get('province_id') or (address.province_id if address else None)
        if not province_id:
            return jsonify({
                'success': False,
                'error': 'province_id es requerido'
            }), 400
        
        crm_province_id = get_crm_province_id_from_province(province_id)
        if not crm_province_id:
            return jsonify({
                'success': False,
                'error': 'No se pudo obtener crm_province_id para la provincia'
            }), 400
        
        city = address_data.get('city') or (address.city if address else '')
        crm_zone_id = data.get('crm_zone_id')
        if not crm_zone_id:
            crm_zone_id = get_crm_zone_id_from_locality(city)
            if not crm_zone_id:
                return jsonify({
                    'success': False,
                    'error': f'No se pudo obtener crm_zone_id para la localidad: {city}'
                }), 400
        
        # Preparar items para la orden (guardaremos los precios ajustados después de calcular el descuento)
        # Por ahora solo guardamos la información básica, los precios se ajustarán después
        items_info = []
        for item in items:
            product_id = uuid.UUID(item['product_id']) if isinstance(item['product_id'], str) else item['product_id']
            product = Product.query.get(product_id)
            if not product:
                continue
            
            variant = ProductVariant.query.filter_by(product_id=product_id).first()
            if not variant:
                continue
            
            option = ProductVariantOption.query.filter_by(product_variant_id=variant.id).first()
            if not option:
                continue
            
            item_id = getattr(option, 'crm_item_id', None) or getattr(variant, 'crm_item_id', None)
            if not item_id and product.crm_product_id:
                item_id = product.crm_product_id
            
            if not item_id:
                continue
            
            # Precio unitario original
            precio_unitario_original = float(item.get('price', 0))
            cantidad = item.get('quantity', 1)
            
            variant_id = None
            if item.get('variant_id'):
                variant_id = uuid.UUID(item['variant_id']) if isinstance(item['variant_id'], str) else item['variant_id']
            
            items_info.append({
                'product_id': str(product_id),
                'variant_id': str(variant_id) if variant_id else None,
                'quantity': cantidad,
                'precio_unitario_original': precio_unitario_original,
                'precio_total_original': precio_unitario_original * cantidad
            })
        
        # Formatear documento
        document_number = formData.get('dni') or formData.get('document_number') or user.dni or ''
        formatted_document = format_document_number(str(doc_type.id), document_number, crm_sale_type_id)
        
        # Construir dirección
        cliente_direccion = f"{address_data.get('street', address.street if address else '')} {address_data.get('number', address.number if address else '')}".strip()
        cliente_direccion_barrio = city
        cliente_direccion_mas_datos = address_data.get('additional_info') or (address.additional_info if address else None)
        
        # Normalizar teléfono
        def normalize_phone(phone_str):
            if not phone_str:
                return "3510000000"
            phone_str = str(phone_str).strip()
            phone_cleaned = ''.join(c for c in phone_str if c.isdigit())
            if phone_cleaned.startswith('0'):
                phone_cleaned = phone_cleaned[1:]
            if len(phone_cleaned) < 8 or len(phone_cleaned) > 11:
                return "3510000000"
            return phone_cleaned
        
        phone_final = normalize_phone(user.phone or address_data.get('phone') or (address.phone if address else ''))
        
        # Calcular el total a pagar (después del descuento de billetera)
        total_a_pagar = float(total)  # Este es el total después del descuento (lo que realmente se paga)
        
        # Calcular el total de productos (sin descuento de billetera)
        # El total que viene del frontend ya tiene el descuento aplicado, así que necesitamos calcular el total original
        # Sumar todos los items: precio unitario * cantidad
        total_productos_original = 0.0
        items_con_precios = []  # Guardar información de cada item para calcular descuento proporcional
        
        for item in items:
            precio_unitario = float(item.get('price', 0))
            cantidad = item.get('quantity', 1)
            precio_total_item = precio_unitario * cantidad
            total_productos_original += precio_total_item
            
            items_con_precios.append({
                'item': item,
                'precio_total_original': precio_total_item,
                'precio_unitario_original': precio_unitario,
                'cantidad': cantidad
            })
        
        # Si hay descuento de billetera, dividirlo proporcionalmente entre los productos
        # EXCEPTO si el método de pago es wallet completo, en cuyo caso se envían los precios originales
        descuento_total = float(used_wallet_amount) if used_wallet_amount and used_wallet_amount > 0 else 0.0
        es_pago_wallet_completo = payment_method == 'wallet'
        
        # Ajustar precios de los items proporcionalmente para el CRM
        # Si es pago completo con wallet, NO ajustar precios (enviar precios originales)
        js_items = []
        for item_info in items_con_precios:
            item = item_info['item']
            precio_total_original = item_info['precio_total_original']
            precio_unitario_original = item_info['precio_unitario_original']
            cantidad = item_info['cantidad']
            
            product_id = uuid.UUID(item['product_id']) if isinstance(item['product_id'], str) else item['product_id']
            product = Product.query.get(product_id)
            if not product:
                continue
            
            variant = ProductVariant.query.filter_by(product_id=product_id).first()
            if not variant:
                continue
            
            option = ProductVariantOption.query.filter_by(product_variant_id=variant.id).first()
            if not option:
                continue
            
            item_id = getattr(option, 'crm_item_id', None) or getattr(variant, 'crm_item_id', None)
            if not item_id and product.crm_product_id:
                item_id = product.crm_product_id
            
            if not item_id:
                continue
            
            # Si es pago completo con wallet, usar precios originales (sin ajuste)
            if es_pago_wallet_completo:
                precio_total_ajustado = precio_total_original
                precio_unitario_ajustado = precio_unitario_original
                print(f"[DEBUG] Producto '{product.name}': pago completo con wallet, usando precio original={precio_total_original}")
            # Si hay descuento de billetera (pero no es pago completo), calcular descuento proporcional
            elif descuento_total > 0 and total_productos_original > 0:
                # Porcentaje que representa este producto del total
                porcentaje_producto = precio_total_original / total_productos_original
                # Descuento que le corresponde a este producto
                descuento_producto = descuento_total * porcentaje_producto
                # Precio ajustado: precio original - descuento proporcional
                precio_total_ajustado = precio_total_original - descuento_producto
                precio_unitario_ajustado = precio_total_ajustado / cantidad if cantidad > 0 else 0
                
                print(f"[DEBUG] Producto '{product.name}': precio_original={precio_total_original}, descuento={descuento_producto:.2f}, precio_ajustado={precio_total_ajustado:.2f}")
            else:
                # No hay descuento, usar precios originales
                precio_total_ajustado = precio_total_original
                precio_unitario_ajustado = precio_unitario_original
            
            js_items.append({
                "id": None,
                "accion": "N",
                "item_id": item_id,
                "cantidad_recibida": cantidad,
                "precio": precio_total_ajustado,  # Precio TOTAL (original si es wallet completo, ajustado si es descuento parcial)
                "unitario_sin_fpago": precio_unitario_ajustado,  # Precio unitario
                "descripcion": product.name
            })
        
        if not js_items:
            return jsonify({
                'success': False,
                'error': 'No se pudieron mapear los productos al CRM'
            }), 400
        
        # Preparar order_items con precios
        # Si es pago completo con wallet, usar precios originales
        # Si es descuento parcial, usar precios ajustados
        order_items_for_payload = []
        for idx, item_info in enumerate(items_info):
            if es_pago_wallet_completo:
                # Pago completo con wallet: usar precios originales
                precio_unitario_final = item_info['precio_unitario_original']
            elif descuento_total > 0 and total_productos_original > 0:
                # Descuento parcial: calcular precio ajustado
                porcentaje_item = item_info['precio_total_original'] / total_productos_original
                descuento_item = descuento_total * porcentaje_item
                precio_total_ajustado = item_info['precio_total_original'] - descuento_item
                precio_unitario_final = precio_total_ajustado / item_info['quantity'] if item_info['quantity'] > 0 else 0
            else:
                # Sin descuento: usar precios originales
                precio_unitario_final = item_info['precio_unitario_original']
            
            order_items_for_payload.append({
                'product_id': item_info['product_id'],
                'variant_id': item_info['variant_id'],
                'quantity': item_info['quantity'],
                'price': precio_unitario_final  # Precio unitario (original si es wallet completo, ajustado si es descuento parcial)
            })
        
        # Verificar y descontar saldo de billetera ANTES de crear la orden
        wallet_movement = None  # Guardar referencia al movimiento para poder revertirlo si hay error
        wallet = None
        if used_wallet_amount and used_wallet_amount > 0:
            try:
                from models.wallet import Wallet, WalletMovement
                from routes.wallet import calculate_wallet_balance
                
                # Obtener o crear wallet del usuario
                wallet = Wallet.query.filter_by(user_id=user.id).first()
                if not wallet:
                    wallet = Wallet(user_id=user.id, balance=0)
                    db.session.add(wallet)
                    db.session.flush()
                
                # Verificar que tenga saldo suficiente
                current_balance = calculate_wallet_balance(wallet.id, include_expired=False)
                if current_balance < used_wallet_amount:
                    return jsonify({
                        'success': False,
                        'error': f'Saldo insuficiente en billetera. Saldo disponible: ${current_balance:.2f}, requerido: ${used_wallet_amount:.2f}'
                    }), 400
                
                # Crear movimiento de débito (pero aún no hacer commit, lo haremos después de crear la orden)
                wallet_movement = WalletMovement(
                    wallet_id=wallet.id,
                    type='order_payment',
                    amount=-float(used_wallet_amount),  # Negativo para que reste del balance
                    description=f'Pago de orden (pendiente)',
                    order_id=None  # Se actualizará después de crear la orden
                )
                db.session.add(wallet_movement)
                db.session.flush()  # Flush para obtener el ID del movimiento y que esté disponible para calcular el balance
                
                # Actualizar balance de la wallet (recalcular después de agregar el movimiento)
                # Esto actualiza el balance en memoria, pero no se hace commit hasta después de crear la orden
                wallet.balance = calculate_wallet_balance(wallet.id, include_expired=False)
                wallet.updated_at = datetime.utcnow()
                
                nuevo_balance = float(wallet.balance)
                print(f"[DEBUG] ✅ Movimiento de billetera creado. Descontando ${used_wallet_amount:.2f}. Balance antes: ${current_balance:.2f}, Balance después: ${nuevo_balance:.2f}")
            except Exception as wallet_error:
                db.session.rollback()
                import traceback
                print(f"[DEBUG] ⚠️ Error al verificar/descontar saldo de billetera: {str(wallet_error)}")
                print(traceback.format_exc())
                return jsonify({
                    'success': False,
                    'error': f'Error al procesar el descuento de billetera: {str(wallet_error)}'
                }), 500
        
        # Determinar medio de pago principal
        # Si el método es wallet, usar medios_pago_id = 3 (o el ID que corresponda para wallet en tu CRM)
        # Si es card, usar 2 (Tarjeta)
        # Si es abonar al recibir, usar 1
        if payment_method == 'wallet':
            medios_pago_id = 3  # Wallet (ajustar según tu CRM si es diferente)
        elif payment_method == 'card':
            medios_pago_id = 2  # Tarjeta
        else:
            medios_pago_id = 1  # Abonar al recibir
        
        # Construir formaPagos: solo el método de pago principal con el total a pagar
        # Si es pago completo con wallet, usar el total original (no el total después del descuento)
        # Si es descuento parcial, usar el total después del descuento
        monto_total_pago = total_productos_original if es_pago_wallet_completo else total_a_pagar
        
        forma_pagos_array = [{
            "medios_pago_id": medios_pago_id,
            "monto_total": monto_total_pago,  # Total original si es wallet completo, total después del descuento si es parcial
            "procesado": payment_method == 'wallet' or (not pay_on_delivery)  # True si ya se pagó (wallet o tarjeta), False si es "abonar al recibir"
        }]
        
        # Preparar payload para /api/ventas/crear
        venta_payload = {
            "fecha_detalle": get_argentina_time().strftime('%Y-%m-%d'),
            "tipo_venta": crm_sale_type_id,
            "cliente_nombre": f"{user.first_name or ''} {user.last_name or ''}".strip() or "Cliente",
            "cliente_direccion": cliente_direccion or "",
            "cliente_direccion_barrio": cliente_direccion_barrio or "",
            "cliente_direccion_mas_datos": cliente_direccion_mas_datos,
            "tipo_documento_cliente": crm_doc_type_id_int,
            "documento_cliente": formatted_document or "",
            "cliente_telefono": phone_final or "",
            "cel_alternativo": None,
            "email_cliente": user.email or "",
            "provincia_id": crm_province_id,
            "localidad": city or "",
            "zona_id": crm_zone_id,
            "observaciones": "",
            "lat_long": {"latitud": 0.0, "longitud": 0.0},
            "js": js_items,  # Items con precios ajustados si hay descuento de billetera
            "formaPagos": forma_pagos_array,  # Solo el método de pago principal con el total a pagar
            # Datos adicionales para crear la orden
            "user_id": str(user.id),
            "payment_method": payment_method,
            "payment_processed": payment_method == 'wallet' or (not pay_on_delivery),  # True si wallet o tarjeta, False si abonar al recibir
            "used_wallet_amount": used_wallet_amount,
            "order_items": order_items_for_payload
        }
        
        # Llamar a /api/ventas/crear
        print(f"[DEBUG] Llamando a /api/ventas/crear para crear orden y venta en CRM...")
        print(f"[DEBUG] Payload completo: {json.dumps(venta_payload, indent=2, default=str)}")
        try:
            from flask import current_app
            from routes.public_api import crear_venta
            
            with current_app.test_request_context(
                '/api/ventas/crear',
                method='POST',
                json=venta_payload,
                headers={'Authorization': f'Bearer {Config.API_KEY}'}
            ):
                response = crear_venta()
                
                if isinstance(response, tuple):
                    response_obj, status_code = response
                else:
                    response_obj = response
                    status_code = response_obj.status_code if hasattr(response_obj, 'status_code') else 200
                
                if hasattr(response_obj, 'get_json'):
                    response_data = response_obj.get_json()
                elif hasattr(response_obj, 'data'):
                    response_data = json.loads(response_obj.data.decode('utf-8'))
                else:
                    response_data = response_obj if isinstance(response_obj, dict) else {}
                
                print(f"[DEBUG] Respuesta de crear_venta: status_code={status_code}, response_data={json.dumps(response_data, indent=2, default=str)}")
                
                if status_code == 200 and response_data.get('status', False):
                    order_id = response_data.get('data', {}).get('order_id')
                    crm_order_id = response_data.get('data', {}).get('crm_order_id')
                    
                    if order_id:
                        # Obtener la orden creada - usar refresh para asegurar que tenemos los datos más recientes
                        order = Order.query.get(uuid.UUID(order_id))
                        if order:
                            # Refrescar para asegurar que tenemos todos los datos actualizados
                            db.session.refresh(order)
                            print(f"[DEBUG] ✅ Orden y venta creadas exitosamente - order_id={order_id}, crm_order_id={crm_order_id}")
                            print(f"[DEBUG] ✅ Orden recuperada - total={order.total}, status={order.status}, payment_method={order.payment_method}")
                        else:
                            return jsonify({
                                'success': False,
                                'error': 'Orden creada pero no se pudo recuperar'
                            }), 500
                    else:
                        return jsonify({
                            'success': False,
                            'error': 'No se recibió order_id en la respuesta'
                        }), 500
                else:
                    error_msg = response_data.get('message', 'Error desconocido al crear venta')
                    
                    # No guardar en sale_retry_queue si es error de stock
                    es_error_stock = (
                        'este artículo no tiene stock' in error_msg or
                        'No se pudo obtener el precio de compra' in error_msg or
                        'compras previas registradas' in error_msg
                    )
                    
                    # Si el error indica que la venta se creó localmente pero falló en endpoint externo,
                    # guardar en la tabla de reintentos (excepto si es error de stock)
                    if 'Venta creada localmente, pero falló en endpoint externo' in error_msg and not es_error_stock:
                        try:
                            from models.sale_retry_queue import SaleRetryQueue
                            from datetime import datetime as dt
                            
                            # Extraer campos del payload para facilitar consultas
                            fecha_detalle = None
                            if venta_payload and venta_payload.get('fecha_detalle'):
                                try:
                                    fecha_detalle = dt.strptime(venta_payload['fecha_detalle'], '%Y-%m-%d').date()
                                except:
                                    pass
                            
                            # Obtener user_id si está disponible
                            user_id_uuid = None
                            if venta_payload and venta_payload.get('user_id'):
                                try:
                                    user_id_uuid = uuid.UUID(venta_payload['user_id']) if isinstance(venta_payload['user_id'], str) else venta_payload['user_id']
                                except:
                                    pass
                            
                            # Obtener order_id si existe (puede que se haya creado antes del error)
                            order_id_uuid = None
                            order_id_from_response = response_data.get('data', {}).get('order_id')
                            if order_id_from_response:
                                try:
                                    order_id_uuid = uuid.UUID(order_id_from_response) if isinstance(order_id_from_response, str) else order_id_from_response
                                except:
                                    pass
                            
                            # Calcular monto_total desde formaPagos
                            monto_total = None
                            if venta_payload and venta_payload.get('formaPagos'):
                                forma_pagos = venta_payload['formaPagos']
                                if isinstance(forma_pagos, list) and len(forma_pagos) > 0:
                                    monto_total = forma_pagos[0].get('monto_total')
                            
                            # Obtener información del error externo
                            external_api_info = response_data.get('external_api', {})
                            error_details = external_api_info if external_api_info else None
                            
                            # Crear registro en sale_retry_queue
                            retry_record = SaleRetryQueue(
                                order_id=order_id_uuid,
                                status='pending',
                                retry_count=0,
                                max_retries=5,
                                error_message=error_msg,
                                error_details=error_details,
                                crm_payload=venta_payload,
                                fecha_detalle=fecha_detalle,
                                tipo_venta=venta_payload.get('tipo_venta') if venta_payload else None,
                                cliente_nombre=venta_payload.get('cliente_nombre') if venta_payload else None,
                                cliente_email=venta_payload.get('email_cliente') if venta_payload else None,
                                provincia_id=venta_payload.get('provincia_id') if venta_payload else None,
                                zona_id=venta_payload.get('zona_id') if venta_payload else None,
                                monto_total=monto_total,
                                payment_method=venta_payload.get('payment_method') if venta_payload else None,
                                payment_processed=venta_payload.get('payment_processed') if venta_payload else None,
                                user_id=user_id_uuid,
                                priority=0
                            )
                            db.session.add(retry_record)
                            db.session.commit()
                            print(f"[DEBUG] ✅ Venta guardada en sale_retry_queue con id={retry_record.id} debido a fallo en endpoint externo")
                        except Exception as retry_error:
                            db.session.rollback()
                            import traceback
                            print(f"[DEBUG] ⚠️ Error al guardar en sale_retry_queue: {str(retry_error)}")
                            print(traceback.format_exc())
                            # No fallar si no se puede guardar en la cola de reintentos
                    
                    # Si hay error y se creó un movimiento de billetera, revertirlo
                    if wallet_movement:
                        try:
                            from routes.wallet import calculate_wallet_balance
                            db.session.delete(wallet_movement)
                            if wallet:
                                wallet.balance = calculate_wallet_balance(wallet.id, include_expired=False)
                                wallet.updated_at = datetime.utcnow()
                            db.session.commit()
                            print(f"[DEBUG] ✅ Movimiento de billetera revertido debido a error al crear la orden: {error_msg}")
                        except Exception as revert_error:
                            db.session.rollback()
                            print(f"[DEBUG] ⚠️ Error al revertir movimiento de billetera: {str(revert_error)}")
                    
                    return jsonify({
                        'success': False,
                        'error': error_msg
                    }), status_code
        except Exception as venta_error:
            import traceback
            print(f"[DEBUG] ⚠️ Error al llamar a /api/ventas/crear: {str(venta_error)}")
            print(traceback.format_exc())
            
            # Si hay error y se creó un movimiento de billetera, revertirlo
            if wallet_movement:
                try:
                    from routes.wallet import calculate_wallet_balance
                    db.session.delete(wallet_movement)
                    if wallet:
                        wallet.balance = calculate_wallet_balance(wallet.id, include_expired=False)
                        wallet.updated_at = datetime.utcnow()
                    db.session.commit()
                    print(f"[DEBUG] ✅ Movimiento de billetera revertido debido a excepción al crear la orden")
                except Exception as revert_error:
                    db.session.rollback()
                    print(f"[DEBUG] ⚠️ Error al revertir movimiento de billetera: {str(revert_error)}")
            
            return jsonify({
                'success': False,
                'error': f'Error al crear orden: {str(venta_error)}'
            }), 500
        
        try:
            # Actualizar el movimiento de billetera con el order_id si existe
            if used_wallet_amount and used_wallet_amount > 0:
                try:
                    from models.wallet import Wallet, WalletMovement
                    from routes.wallet import calculate_wallet_balance
                    
                    # Buscar el movimiento de billetera que creamos antes (el más reciente sin order_id)
                    wallet = Wallet.query.filter_by(user_id=user.id).first()
                    if wallet:
                        movement = WalletMovement.query.filter_by(
                            wallet_id=wallet.id,
                            type='order_payment',
                            order_id=None
                        ).order_by(WalletMovement.created_at.desc()).first()
                        
                        if movement:
                            # Actualizar el movimiento con el order_id y la descripción completa
                            movement.order_id = order.id
                            movement.description = f'Pago de orden {str(order.id)[:8]}'
                            
                            # Recalcular el balance de la wallet (por si acaso hay cambios)
                            wallet.balance = calculate_wallet_balance(wallet.id, include_expired=False)
                            wallet.updated_at = datetime.utcnow()
                            
                            # Hacer commit para persistir el movimiento y el balance actualizado
                            db.session.commit()
                            
                            balance_final = float(wallet.balance)
                            print(f"[DEBUG] ✅ Movimiento de billetera registrado y balance actualizado para orden {order.id}")
                            print(f"[DEBUG]    - Tipo: order_payment")
                            print(f"[DEBUG]    - Monto descontado: ${used_wallet_amount:.2f}")
                            print(f"[DEBUG]    - Balance final: ${balance_final:.2f}")
                            print(f"[DEBUG]    - Order ID: {order.id}")
                        else:
                            print(f"[DEBUG] ⚠️ No se encontró movimiento de billetera pendiente para actualizar")
                            # Si no se encontró el movimiento, intentar crearlo de nuevo
                            try:
                                movement = WalletMovement(
                                    wallet_id=wallet.id,
                                    type='order_payment',
                                    amount=-float(used_wallet_amount),
                                    description=f'Pago de orden {str(order.id)[:8]}',
                                    order_id=order.id
                                )
                                db.session.add(movement)
                                wallet.balance = calculate_wallet_balance(wallet.id, include_expired=False)
                                wallet.updated_at = datetime.utcnow()
                                db.session.commit()
                                print(f"[DEBUG] ✅ Movimiento de billetera creado después de crear la orden. Balance: ${wallet.balance}")
                            except Exception as fallback_error:
                                db.session.rollback()
                                print(f"[DEBUG] ⚠️ Error al crear movimiento de billetera como fallback: {str(fallback_error)}")
                except Exception as wallet_error:
                    db.session.rollback()
                    import traceback
                    print(f"[DEBUG] ⚠️ Error al actualizar movimiento de billetera: {str(wallet_error)}")
                    print(traceback.format_exc())
                    # No fallar la orden si falla la actualización del movimiento, pero loguear el error
            
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
                
                # Si no se encontró receipt_number, usar UUID de la orden
                if not order_number:
                    order_number = str(order.id)
                
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
                    
                    # Si la orden tiene un created_at muy antiguo o parece estar en UTC (diferencia > 2 horas),
                    # actualizarlo a la hora de Argentina
                    if existing_order.created_at:
                        now_argentina = get_argentina_time()
                        time_diff = abs((now_argentina - existing_order.created_at).total_seconds() / 3600)
                        # Si la diferencia es mayor a 2 horas, probablemente está en UTC, actualizar
                        if time_diff > 2:
                            existing_order.created_at = get_argentina_time()
                            print(f"[DEBUG] ⚠️ Actualizado created_at de orden existente (parecía estar en UTC)")
                    
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
                            
                            # Si no se encontró receipt_number, usar UUID de la orden
                            if not order_number:
                                order_number = str(existing_order.id)
                            
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
            # Datos del cardholder del Brick (tienen prioridad sobre los datos del formulario)
            mp_cardholder_name = data.get('mercadopago_cardholder_name')
            mp_cardholder_email = data.get('mercadopago_cardholder_email')
            mp_cardholder_identification_type = data.get('mercadopago_cardholder_identification_type')
            mp_cardholder_identification_number = data.get('mercadopago_cardholder_identification_number')
            
            # ========== DEBUG: Lo que llega del frontend ==========
            print(f"[DEBUG] ========== DATOS DEL FRONTEND ==========")
            print(f"[DEBUG] mercadopago_payment_method_id: {mp_payment_method_id} (tipo: {type(mp_payment_method_id).__name__})")
            print(f"[DEBUG] mercadopago_issuer_id: {mp_issuer_id} (tipo: {type(mp_issuer_id).__name__})")
            print(f"[DEBUG] mercadopago_token: {mp_token[:6] if mp_token and len(mp_token) >= 6 else mp_token}... (longitud: {len(mp_token) if mp_token else 0})")
            print(f"[DEBUG] amount (total): {total} (tipo: {type(total).__name__})")
            print(f"[DEBUG] ========================================")
            
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
                
                # Calcular el total a pagar con tarjeta
                # El 'total' que viene del frontend ya tiene el descuento de billetera aplicado
                # Por lo tanto, total_to_pay es simplemente el total (no hay que restar el descuento de nuevo)
                total_to_pay = float(total)
                
                # Si el total es 0 o negativo, no se puede procesar el pago
                if total_to_pay <= 0:
                    return jsonify({
                        'success': False,
                        'error': 'El monto a pagar con tarjeta debe ser mayor a 0. Si el descuento de billetera cubre todo el total, no se puede pagar con tarjeta.'
                    }), 400
                
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
                # PRIORIDAD: Usar datos del cardholder del Brick si están disponibles (son más confiables)
                # Si no, usar datos del formulario
                
                # Email: Prioridad 1) Cardholder del Brick, 2) Formulario, 3) Usuario, 4) Default
                customer_email = mp_cardholder_email or (formData.get('email', '') if formData else '') or user.email or ''
                if not customer_email or customer_email.strip() == "":
                    customer_email = "test@example.com"
                    print(f"[DEBUG] ⚠️ No se encontró email válido, usando email por defecto")
                
                # Nombre: Prioridad 1) Cardholder del Brick, 2) Formulario
                if mp_cardholder_name:
                    # El cardholder name puede venir como "Nombre Apellido", separarlo
                    name_parts = mp_cardholder_name.strip().split(' ', 1)
                    customer_first_name = name_parts[0] if name_parts else ''
                    customer_last_name = name_parts[1] if len(name_parts) > 1 else ''
                else:
                    customer_first_name = formData.get('first_name', '') if formData else ''
                    customer_last_name = formData.get('last_name', '') if formData else ''
                
                customer_phone = formData.get('phone', '') if formData else ''
                
                # Identificación: Prioridad 1) Cardholder del Brick, 2) Formulario, 3) Address
                identification_type = mp_cardholder_identification_type
                identification_number = mp_cardholder_identification_number
                
                if not identification_number:
                    identification_number = customer_dni
                if not identification_number:
                    identification_number = address_data.get('dni', '')
                
                # Si no hay tipo de identificación pero hay número, usar DNI por defecto
                if not identification_type and identification_number:
                    identification_type = "DNI"
                
                # Construir el objeto payer completo
                payer_data = {}
                
                # Email es obligatorio
                payer_data["email"] = customer_email.strip()
                
                # Identificación (obligatorio para Argentina)
                if identification_type and identification_number:
                    payer_data["identification"] = {
                        "type": identification_type,
                        "number": str(identification_number)
                    }
                
                # Nombre completo
                if customer_first_name:
                    payer_data["first_name"] = customer_first_name
                if customer_last_name:
                    payer_data["last_name"] = customer_last_name
                
                # Teléfono (opcional pero recomendado)
                if customer_phone:
                    # Limpiar el teléfono (remover espacios, guiones, etc.)
                    phone_clean = ''.join(filter(str.isdigit, str(customer_phone)))
                    if phone_clean:
                        payer_data["phone"] = {
                            "number": phone_clean
                        }
                
                print(f"[DEBUG] 🔍 Datos del payer (prioridad: Brick > Formulario > Usuario):")
                print(f"[DEBUG]   - Email: {payer_data.get('email')} (fuente: {'Brick' if mp_cardholder_email else 'Formulario/Usuario'})")
                print(f"[DEBUG]   - Nombre: {payer_data.get('first_name')} {payer_data.get('last_name')} (fuente: {'Brick' if mp_cardholder_name else 'Formulario'})")
                print(f"[DEBUG]   - Identificación: {payer_data.get('identification')} (fuente: {'Brick' if mp_cardholder_identification_number else 'Formulario/Address'})")
                
                print(f"[DEBUG] Payer data construido: {json.dumps(payer_data, indent=2, default=str)}")
                
                # Asegurarse de que payer_data no tenga valores None o vacíos
                payer_data_clean = {}
                for key, value in payer_data.items():
                    if value is not None and value != "":
                        if isinstance(value, dict):
                            # Limpiar diccionarios anidados también
                            nested_clean = {}
                            for nested_key, nested_value in value.items():
                                if nested_value is not None and nested_value != "":
                                    nested_clean[nested_key] = nested_value
                            if nested_clean:
                                payer_data_clean[key] = nested_clean
                        else:
                            payer_data_clean[key] = value
                
                # Asegurarse de que email siempre esté presente (es obligatorio)
                if "email" not in payer_data_clean or not payer_data_clean["email"]:
                    payer_data_clean["email"] = customer_email.strip() if customer_email else "test@example.com"
                
                print(f"[DEBUG] Datos del cliente obtenidos: email={customer_email}, first_name={customer_first_name}, last_name={customer_last_name}, dni={customer_dni}, phone={customer_phone}")
                
                payment_payload = {
                    "token": mp_token_clean,
                    "installments": int(mp_installments),
                    "transaction_amount": float(total_to_pay),
                    "description": f"Orden {str(order.id)[:8]}",
                    "payment_method_id": mp_payment_method_id,
                    "payer": payer_data_clean,
                    "external_reference": str(order.id),
                    "statement_descriptor": "BAUSING"
                }
                
                print(f"[DEBUG] Payment payload payer (limpio): {json.dumps(payer_data_clean, indent=2, default=str)}")
                
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
                issuer_id_final = None
                if mp_issuer_id:
                    try:
                        issuer_id_final = int(mp_issuer_id)
                        payment_payload["issuer_id"] = issuer_id_final
                    except (ValueError, TypeError) as e:
                        print(f"[DEBUG] ⚠️ ERROR: No se pudo convertir issuer_id a int: {mp_issuer_id} (tipo: {type(mp_issuer_id).__name__})")
                        print(f"[DEBUG] ⚠️ ERROR: Exception: {e}")
                
                # ========== DEBUG: Lo que se envía a MercadoPago ==========
                print(f"[DEBUG] ========== DATOS ENVIADOS A MERCADOPAGO ==========")
                print(f"[DEBUG] payment_method_id: {payment_payload.get('payment_method_id')} (tipo: {type(payment_payload.get('payment_method_id')).__name__})")
                print(f"[DEBUG] issuer_id: {issuer_id_final} (tipo: {type(issuer_id_final).__name__ if issuer_id_final is not None else 'None'})")
                print(f"[DEBUG] payer.email: {payer_data_clean.get('email')} (tipo: {type(payer_data_clean.get('email')).__name__ if payer_data_clean.get('email') else 'None'})")
                print(f"[DEBUG] transaction_amount: {payment_payload.get('transaction_amount')} (tipo: {type(payment_payload.get('transaction_amount')).__name__})")
                print(f"[DEBUG] ===================================================")
                
                # ========== VERIFICACIÓN DE COINCIDENCIA ==========
                if mp_payment_method_id != payment_payload.get('payment_method_id'):
                    print(f"[DEBUG] ⚠️ ERROR: payment_method_id NO COINCIDE!")
                    print(f"[DEBUG]   Frontend: {mp_payment_method_id}")
                    print(f"[DEBUG]   Backend: {payment_payload.get('payment_method_id')}")
                else:
                    print(f"[DEBUG] ✅ payment_method_id coincide: {mp_payment_method_id}")
                
                if mp_issuer_id is None and issuer_id_final is not None:
                    print(f"[DEBUG] ⚠️ ADVERTENCIA: issuer_id viene undefined del frontend pero se está enviando: {issuer_id_final}")
                elif mp_issuer_id is not None and issuer_id_final is None:
                    print(f"[DEBUG] ⚠️ ERROR: issuer_id viene del frontend ({mp_issuer_id}) pero NO se está enviando!")
                elif mp_issuer_id is not None and issuer_id_final is not None:
                    if int(mp_issuer_id) != issuer_id_final:
                        print(f"[DEBUG] ⚠️ ERROR: issuer_id NO COINCIDE!")
                        print(f"[DEBUG]   Frontend: {mp_issuer_id} (int: {int(mp_issuer_id)})")
                        print(f"[DEBUG]   Backend: {issuer_id_final}")
                    else:
                        print(f"[DEBUG] ✅ issuer_id coincide: {issuer_id_final}")
                else:
                    print(f"[DEBUG] ℹ️ issuer_id no está presente (es opcional)")
                
                # Generar idempotency key único para este pago (usar el ID de la orden)
                idempotency_key = str(order.id)
                
                # ========== VERIFICACIÓN DE CAMPOS MÍNIMOS REQUERIDOS (según documentación oficial) ==========
                campos_minimos_requeridos = {
                    "token": mp_token_clean,
                    "transaction_amount": float(total_to_pay),
                    "installments": int(mp_installments),
                    "payment_method_id": mp_payment_method_id,
                    "payer.email": payer_data_clean.get('email')
                }
                
                campos_faltantes = []
                for campo, valor in campos_minimos_requeridos.items():
                    if valor is None or valor == "":
                        campos_faltantes.append(campo)
                
                if campos_faltantes:
                    print(f"[DEBUG] ❌ ERROR: Faltan campos mínimos requeridos por MercadoPago: {', '.join(campos_faltantes)}")
                    return jsonify({
                        'success': False,
                        'error': f'Faltan campos requeridos para el pago: {", ".join(campos_faltantes)}'
                    }), 400
                else:
                    print(f"[DEBUG] ✅ Todos los campos mínimos requeridos están presentes:")
                    print(f"[DEBUG]   - token: {'✅' if mp_token_clean else '❌'}")
                    print(f"[DEBUG]   - transaction_amount: {'✅' if float(total_to_pay) > 0 else '❌'} ({total_to_pay})")
                    print(f"[DEBUG]   - installments: {'✅' if int(mp_installments) > 0 else '❌'} ({mp_installments})")
                    print(f"[DEBUG]   - payment_method_id: {'✅' if mp_payment_method_id else '❌'} ({mp_payment_method_id})")
                    print(f"[DEBUG]   - payer.email: {'✅' if payer_data_clean.get('email') else '❌'} ({payer_data_clean.get('email')})")
                
                # Log del payload completo (sin mostrar el token completo por seguridad)
                payload_log = payment_payload.copy()
                if 'token' in payload_log:
                    payload_log['token'] = f"{payload_log['token'][:20]}... (oculto)"
                print(f"[DEBUG] Payload completo a enviar a MercadoPago: {json.dumps(payload_log, indent=2, default=str)}")
                print(f"[DEBUG] Payer completo en payload (verificación): {json.dumps(payment_payload.get('payer', {}), indent=2, default=str)}")
                print(f"[DEBUG] Email en payer: {payment_payload.get('payer', {}).get('email', 'NO ENCONTRADO')}")
                print(f"[DEBUG] Identification en payer: {payment_payload.get('payer', {}).get('identification', 'NO ENCONTRADO')}")
                print(f"[DEBUG] First name en payer: {payment_payload.get('payer', {}).get('first_name', 'NO ENCONTRADO')}")
                print(f"[DEBUG] Last name en payer: {payment_payload.get('payer', {}).get('last_name', 'NO ENCONTRADO')}")
                
                # Verificar que el objeto payer esté correctamente formateado antes de enviar
                payer_in_payload = payment_payload.get('payer', {})
                print(f"[DEBUG] 🔍 Verificación final del payer antes de enviar:")
                print(f"[DEBUG]   - Email: {payer_in_payload.get('email', 'NO ENCONTRADO')}")
                print(f"[DEBUG]   - Identification: {payer_in_payload.get('identification', 'NO ENCONTRADO')}")
                print(f"[DEBUG]   - First name: {payer_in_payload.get('first_name', 'NO ENCONTRADO')}")
                print(f"[DEBUG]   - Last name: {payer_in_payload.get('last_name', 'NO ENCONTRADO')}")
                print(f"[DEBUG]   - Phone: {payer_in_payload.get('phone', 'NO ENCONTRADO')}")
                
                # Serializar el payload a JSON para verificar que se serializa correctamente
                payload_json = json.dumps(payment_payload, default=str)
                print(f"[DEBUG] Payload JSON serializado (primeros 500 caracteres): {payload_json[:500]}")
                
                # Verificar que el objeto payer esté presente y correcto antes de enviar
                payer_in_payload = payment_payload.get('payer', {})
                if not payer_in_payload or not payer_in_payload.get('email'):
                    print(f"[DEBUG] ⚠️ ERROR: El objeto payer no tiene email o está vacío!")
                    print(f"[DEBUG] Payer en payload: {payer_in_payload}")
                else:
                    print(f"[DEBUG] ✅ Payer verificado antes de enviar: email={payer_in_payload.get('email')}")
                
                # Serializar manualmente para verificar el JSON
                try:
                    payload_json_str = json.dumps(payment_payload, default=str, ensure_ascii=False)
                    # Verificar que el payer esté en el JSON serializado
                    if '"payer"' in payload_json_str and '"email"' in payload_json_str:
                        print(f"[DEBUG] ✅ Payer encontrado en JSON serializado")
                        # Mostrar solo la parte del payer en el JSON
                        import re
                        payer_match = re.search(r'"payer"\s*:\s*\{[^}]*\}', payload_json_str)
                        if payer_match:
                            print(f"[DEBUG] Payer en JSON: {payer_match.group(0)[:200]}...")
                    else:
                        print(f"[DEBUG] ⚠️ ERROR: Payer NO encontrado en JSON serializado!")
                except Exception as e:
                    print(f"[DEBUG] ⚠️ Error al serializar JSON: {e}")
                
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
                else:
                    # Incluso si es 201, verificar el payer en la respuesta
                    response_data = mp_response.json()
                    payer_in_response = response_data.get('payer', {})
                    print(f"[DEBUG] 🔍 Payer en la respuesta de MercadoPago:")
                    print(f"[DEBUG]   - Email: {payer_in_response.get('email', 'NULL')}")
                    print(f"[DEBUG]   - Identification: {payer_in_response.get('identification', 'NULL')}")
                    print(f"[DEBUG]   - First name: {payer_in_response.get('first_name', 'NULL')}")
                    print(f"[DEBUG]   - Last name: {payer_in_response.get('last_name', 'NULL')}")
                
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
                        
                        # Retornar la orden con la estructura estándar
                        return jsonify({
                            'success': True,
                            'data': order.to_dict(),
                            'message': 'Orden creada y pago aprobado exitosamente'
                        }), 201
                    elif payment_status == 'pending' or payment_status == 'in_process':
                        # El pago está pendiente o en proceso, se procesará vía webhook
                        status_detail = mp_payment.get('status_detail', '')
                        if status_detail == 'pending_contingency':
                            print(f"[DEBUG] ⚠️ Pago en proceso (pending_contingency) - MercadoPago está revisando el pago")
                            print(f"[DEBUG] ⚠️ Este estado es común en pagos de prueba. El pago puede ser aprobado o rechazado más tarde.")
                            print(f"[DEBUG] ⚠️ El webhook notificará cuando el estado cambie.")
                        else:
                            print(f"[DEBUG] ⚠️ Pago pendiente (status: {payment_status}, detail: {status_detail}), esperando webhook")
                        
                        # Marcar la orden como pendiente de pago
                        order.payment_processed = False
                        order.status = 'pending'
                        db.session.commit()
                        
                        # Retornar éxito pero indicando que el pago está pendiente
                        # IMPORTANTE: Retornar la estructura estándar con 'data' usando order.to_dict() para consistencia
                        # El order.to_dict() ya incluye el 'id' (UUID de la orden), no el payment_id
                        order_dict = order.to_dict()
                        # Agregar información adicional del pago sin sobrescribir el 'id'
                        order_dict['payment_status'] = payment_status
                        order_dict['payment_id'] = payment_id  # ID de MercadoPago (solo para referencia, NO usar para acceder a la orden)
                        order_dict['status_detail'] = status_detail
                        order_dict['pending'] = True
                        
                        return jsonify({
                            'success': True,
                            'message': 'Orden creada exitosamente. El pago está siendo procesado por MercadoPago.',
                            'data': order_dict  # Incluye 'id' que es el UUID de la orden
                        }), 201
                    else:
                        # Pago rechazado o en otro estado
                        # Construir mensaje de error más descriptivo
                        error_msg = f'El pago fue {payment_status}'
                        if status_detail:
                            error_msg += f' ({status_detail})'
                        if error_message_mp:
                            error_msg += f': {error_message_mp}'
                        else:
                            # Mensajes más específicos según el motivo del rechazo
                            if status_detail == 'cc_rejected_other_reason':
                                error_msg += '. Posibles causas:\n'
                                error_msg += '1. Monto muy bajo (prueba con más de $10 ARS)\n'
                                error_msg += '2. Tarjeta asociada a tu cuenta de MercadoPago\n'
                                error_msg += '3. Cuenta no configurada como vendedor (necesitas activar cuenta vendedor)\n'
                                error_msg += '4. Tarjeta de prueba no válida para este monto'
                            else:
                                error_msg += '. Por favor, intenta con otra tarjeta o verifica los datos de la tarjeta.'
                        
                        print(f"[DEBUG] ❌ Pago rechazado: {error_msg}")
                        print(f"[DEBUG] Detalles completos del pago: {json.dumps(mp_payment, indent=2, default=str)}")
                        print(f"[DEBUG] Monto enviado: {total_to_pay} ARS")
                        print(f"[DEBUG] ⚠️ NOTA: El objeto payer en la respuesta aparece como null porque MercadoPago usa la información del token del Card Payment Brick")
                        
                        # Marcar la orden como no pagada
                        order.payment_processed = False
                        order.status = 'pending'
                        db.session.commit()
                        
                        # Si hay un movimiento de billetera asociado a esta orden, revertirlo
                        if order.used_wallet_amount and order.used_wallet_amount > 0:
                            try:
                                from models.wallet import WalletMovement
                                from routes.wallet import calculate_wallet_balance
                                
                                # Buscar el movimiento de billetera asociado a esta orden
                                movement = WalletMovement.query.filter_by(order_id=order.id, type='order_payment').first()
                                if movement:
                                    wallet = movement.wallet
                                    db.session.delete(movement)
                                    wallet.balance = calculate_wallet_balance(wallet.id, include_expired=False)
                                    wallet.updated_at = datetime.utcnow()
                                    db.session.commit()
                                    print(f"[DEBUG] ✅ Movimiento de billetera revertido debido a pago rechazado con tarjeta para orden {order.id}")
                            except Exception as revert_error:
                                db.session.rollback()
                                print(f"[DEBUG] ⚠️ Error al revertir movimiento de billetera por pago rechazado: {str(revert_error)}")
                        
                        return jsonify({
                            'success': False,
                            'error': error_msg,
                            'payment_status': payment_status,
                            'payment_id': payment_id,
                            'status_detail': status_detail,
                            'amount': total_to_pay
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
