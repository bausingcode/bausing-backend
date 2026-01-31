from flask import Blueprint, request, jsonify
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
                
                # Limpiar teléfono: eliminar espacios y si empieza con 0, quitarlo
                if phone:
                    phone = str(phone).strip()
                    if phone.startswith('0'):
                        phone = phone[1:]
                        print(f"[DEBUG] Teléfono - Eliminado 0 inicial, nuevo valor: '{phone}'")
                
                # Limpiar teléfono alternativo también
                if alternate_phone:
                    alternate_phone = str(alternate_phone).strip()
                    if alternate_phone.startswith('0'):
                        alternate_phone = alternate_phone[1:]
                        print(f"[DEBUG] Teléfono alternativo - Eliminado 0 inicial, nuevo valor: '{alternate_phone}'")
                
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
        
        return jsonify({
            'success': True,
            'data': order_dict,
            'message': 'Orden creada exitosamente'
        }), 201
        
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error al crear orden: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Error al crear orden: {str(e)}'
        }), 500
