from flask import Blueprint, request, jsonify, current_app as app
from database import db
from models.product import Product, ProductVariant, ProductVariantOption, ProductPrice
from models.locality import Locality
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from routes.admin import admin_required
import uuid
from datetime import datetime
import traceback

crm_products_bp = Blueprint('crm_products', __name__)

@crm_products_bp.route('/admin/crm-products', methods=['GET'])
@admin_required
def list_crm_products():
    """
    Listar productos CRM completados y no completados
    
    Query parameters:
    - status: 'completed' | 'not_completed' | 'all' (default: 'all')
    - combo: true/false para filtrar combos
    - search: término de búsqueda (busca en ID CRM, descripción, alt_description, product_name)
    - page: número de página (default: 1)
    - per_page: items por página (default: 20, max: 100)
    """
    try:
        status = request.args.get('status', 'all')
        combo_filter = request.args.get('combo')
        search = request.args.get('search', '').strip()
        
        # Paginación
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        offset = (page - 1) * per_page
        
        # Verificar si la tabla existe
        try:
            test_query = "SELECT 1 FROM crm_products LIMIT 1"
            db.session.execute(text(test_query))
        except Exception as table_error:
            return jsonify({
                'success': False,
                'error': f'La tabla crm_products no existe o no es accesible: {str(table_error)}'
            }), 500
        
        # Construir query base para conteo
        count_query = """
            SELECT COUNT(*)
            FROM crm_products cp
            LEFT JOIN products p ON p.crm_product_id = cp.crm_product_id
        """
        
        # Construir query base para datos
        query = """
            SELECT 
                cp.id,
                cp.crm_product_id,
                cp.combo,
                cp.is_active,
                cp.commission,
                cp.price_sale,
                cp.variability,
                cp.min_limit,
                cp.description,
                cp.alt_description,
                cp.crm_created_at,
                cp.crm_updated_at,
                cp.raw,
                p.id as product_id,
                p.name as product_name
            FROM crm_products cp
            LEFT JOIN products p ON p.crm_product_id = cp.crm_product_id
        """
        
        conditions = []
        params = {}
        
        if status == 'completed':
            conditions.append("p.id IS NOT NULL")
        elif status == 'not_completed':
            conditions.append("p.id IS NULL")
        
        if combo_filter is not None:
            if combo_filter.lower() == 'true':
                conditions.append("cp.combo = true")
            elif combo_filter.lower() == 'false':
                conditions.append("cp.combo = false")
        
        # Búsqueda
        if search:
            search_conditions = [
                "CAST(cp.crm_product_id AS TEXT) ILIKE :search",
                "cp.description ILIKE :search",
                "cp.alt_description ILIKE :search",
                "p.name ILIKE :search"
            ]
            conditions.append(f"({' OR '.join(search_conditions)})")
            params['search'] = f'%{search}%'
        
        where_clause = ""
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)
            count_query += where_clause
            query += where_clause
        
        # Contar total
        count_result = db.session.execute(text(count_query), params)
        total = count_result.scalar()
        
        # Agregar paginación y ordenamiento
        query += " ORDER BY cp.crm_product_id LIMIT :limit OFFSET :offset"
        params['limit'] = per_page
        params['offset'] = offset
        
        result = db.session.execute(text(query), params)
        rows = result.fetchall()
        
        products = []
        for row in rows:
            products.append({
                'id': str(row.id),
                'crm_product_id': row.crm_product_id,
                'combo': row.combo,
                'is_active': row.is_active,
                'commission': float(row.commission) if row.commission else None,
                'price_sale': float(row.price_sale) if row.price_sale else None,
                'variability': float(row.variability) if row.variability else None,
                'min_limit': float(row.min_limit) if row.min_limit else None,
                'description': row.description,
                'alt_description': row.alt_description,
                'crm_created_at': row.crm_created_at.isoformat() if row.crm_created_at else None,
                'crm_updated_at': row.crm_updated_at.isoformat() if row.crm_updated_at else None,
                'product_id': str(row.product_id) if row.product_id else None,
                'product_name': row.product_name,
                'is_completed': row.product_id is not None,
                'raw': row.raw
            })
        
        total_pages = (total + per_page - 1) // per_page
        
        return jsonify({
            'success': True,
            'data': products,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            }
        }), 200
        
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Error en list_crm_products: {error_trace}")
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': error_trace if app.config.get('DEBUG') else None
        }), 500

@crm_products_bp.route('/admin/crm-products/<uuid:product_id>', methods=['GET'])
@admin_required
def get_crm_product(product_id):
    """Obtener un producto CRM por ID"""
    try:
        query = """
            SELECT 
                cp.id,
                cp.crm_product_id,
                cp.combo,
                cp.is_active,
                cp.commission,
                cp.price_sale,
                cp.variability,
                cp.min_limit,
                cp.description,
                cp.alt_description,
                cp.crm_created_at,
                cp.crm_updated_at,
                cp.raw,
                p.id as product_id
            FROM crm_products cp
            LEFT JOIN products p ON p.crm_product_id = cp.crm_product_id
            WHERE cp.id = :product_id
        """
        
        result = db.session.execute(text(query), {'product_id': str(product_id)})
        row = result.fetchone()
        
        if not row:
            return jsonify({
                'success': False,
                'error': 'Producto CRM no encontrado'
            }), 404
        
        product_data = {
            'id': str(row.id),
            'crm_product_id': row.crm_product_id,
            'combo': row.combo,
            'is_active': row.is_active,
            'commission': float(row.commission) if row.commission else None,
            'price_sale': float(row.price_sale) if row.price_sale else None,
            'variability': float(row.variability) if row.variability else None,
            'min_limit': float(row.min_limit) if row.min_limit else None,
            'description': row.description,
            'alt_description': row.alt_description,
            'crm_created_at': row.crm_created_at.isoformat() if row.crm_created_at else None,
            'crm_updated_at': row.crm_updated_at.isoformat() if row.crm_updated_at else None,
            'product_id': str(row.product_id) if row.product_id else None,
            'is_completed': row.product_id is not None,
            'raw': row.raw
        }
        
        # Si está completado, obtener datos del producto
        if row.product_id:
            product = Product.query.get(row.product_id)
            if product:
                product_data['product'] = product.to_dict(include_images=True, include_variants=True)
        
        return jsonify({
            'success': True,
            'data': product_data
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@crm_products_bp.route('/admin/crm-products/<uuid:product_id>/complete', methods=['POST', 'PUT'])
@admin_required
def complete_crm_product(product_id):
    """
    Completar/vincular un producto CRM con un producto del ecommerce
    
    Body:
    {
        "product_id": "uuid" (opcional, si no se proporciona se crea uno nuevo)
        ... datos del producto (name, description, category_id, etc.)
    }
    """
    try:
        data = request.get_json()
        
        # Obtener producto CRM
        query = """
            SELECT cp.crm_product_id, cp.combo
            FROM crm_products cp
            WHERE cp.id = :product_id
        """
        result = db.session.execute(text(query), {'product_id': str(product_id)})
        crm_row = result.fetchone()
        
        if not crm_row:
            return jsonify({
                'success': False,
                'error': 'Producto CRM no encontrado'
            }), 404
        
        crm_product_id_int = crm_row.crm_product_id
        
        # Verificar si ya está vinculado usando SQL directo (evita error si columnas no existen)
        check_query = """
            SELECT id FROM products WHERE crm_product_id = :crm_product_id LIMIT 1
        """
        check_result = db.session.execute(text(check_query), {'crm_product_id': crm_product_id_int})
        existing_product_id = check_result.scalar()
        
        if existing_product_id and not data.get('product_id'):
            return jsonify({
                'success': False,
                'error': 'El producto CRM ya está vinculado a un producto'
            }), 400
        
        # Obtener o crear producto
        if data.get('product_id'):
            product = Product.query.get(data['product_id'])
            if not product:
                return jsonify({
                    'success': False,
                    'error': 'Producto no encontrado'
                }), 404
            # Actualizar producto existente
            for key, value in data.items():
                if key != 'product_id' and hasattr(product, key):
                    setattr(product, key, value)
            product.crm_product_id = crm_product_id_int
        else:
            # Crear nuevo producto
            # Determinar si es combo basado en el crm_product usando SQL directo
            combo_query = """
                SELECT combo FROM crm_products WHERE crm_product_id = :crm_product_id LIMIT 1
            """
            combo_result = db.session.execute(text(combo_query), {'crm_product_id': crm_product_id_int})
            combo_row = combo_result.fetchone()
            is_combo = combo_row.combo if combo_row else False
            
            product = Product(
                name=data.get('name', ''),
                description=data.get('description'),
                technical_description=data.get('technical_description'),
                warranty_months=data.get('warranty_months'),
                warranty_description=data.get('warranty_description'),
                materials=data.get('materials'),
                filling_type=data.get('filling_type'),
                max_supported_weight_kg=data.get('max_supported_weight_kg'),
                has_pillow_top=data.get('has_pillow_top', False),
                is_bed_in_box=data.get('is_bed_in_box', False),
                mattress_firmness=data.get('mattress_firmness'),
                size_label=data.get('size_label'),
                sku=data.get('sku'),
                crm_product_id=crm_product_id_int,
                category_id=uuid.UUID(data['category_id']) if data.get('category_id') else None,
                category_option_id=uuid.UUID(data['category_option_id']) if data.get('category_option_id') else None,
                is_combo=is_combo,
                is_active=data.get('is_active', True)
            )
            db.session.add(product)
        
        db.session.flush()  # Para obtener el ID del producto
        
        # Crear variantes y precios si se proporcionaron
        if data.get('variants'):
            # Eliminar variantes existentes si es actualización
            if data.get('product_id'):
                # Eliminar options primero (por foreign key)
                variants_to_delete = ProductVariant.query.filter_by(product_id=product.id).all()
                for v in variants_to_delete:
                    ProductVariantOption.query.filter_by(product_variant_id=v.id).delete()
                ProductVariant.query.filter_by(product_id=product.id).delete()
                db.session.flush()
            
            variants_data = data.get('variants', [])
            # Primero, agrupar todas las options por atributo
            variants_dict = {}  # {attr_name: {variant_obj, options: {attr_value: {stock, prices}}}}
            
            for idx, variant_data in enumerate(variants_data):
                attributes = variant_data.get('attributes', {})
                prices_data = variant_data.get('prices', [])
                stock = variant_data.get('stock', 0)
                
                # Para cada atributo en esta variant_data
                for attr_name, attr_value in attributes.items():
                    # Si no existe la variant para este atributo, crearla
                    if attr_name not in variants_dict:
                        variant = ProductVariant(
                            product_id=product.id,
                            sku=attr_name,  # Nombre del atributo (ej: "Tamaño")
                            price=None
                        )
                        db.session.add(variant)
                        db.session.flush()
                        variants_dict[attr_name] = {
                            'variant': variant,
                            'options': {}
                        }
                    
                    # Si no existe la option para este valor, crearla o actualizar stock
                    if attr_value not in variants_dict[attr_name]['options']:
                        option = ProductVariantOption(
                            product_variant_id=variants_dict[attr_name]['variant'].id,
                            name=attr_value,  # Valor de la opción (ej: "M")
                            stock=stock
                        )
                        db.session.add(option)
                        db.session.flush()
                        variants_dict[attr_name]['options'][attr_value] = {
                            'option': option,
                            'prices': prices_data.copy()
                        }
                    else:
                        # Si ya existe, sumar el stock (o manejar como prefieras)
                        existing_option = variants_dict[attr_name]['options'][attr_value]['option']
                        existing_option.stock += stock
            
            # Ahora crear los precios para cada variant (compartidos entre todas las options)
            created_variants = []
            for attr_name, variant_info in variants_dict.items():
                variant = variant_info['variant']
                created_prices = []
                prices_added = set()  # Para evitar duplicados en la misma transacción
                
                # Agrupar precios únicos de todas las options de esta variant
                # Recopilar todos los precios únicos de todas las options
                all_prices_data = []
                for option_data in variant_info['options'].values():
                    for price_data in option_data['prices']:
                        locality_id = price_data.get('locality_id')
                        price_value = price_data.get('price')
                        if locality_id and price_value is not None:
                            price_key = (locality_id, float(price_value))
                            if price_key not in prices_added:
                                all_prices_data.append(price_data)
                                prices_added.add(price_key)
                
                # Crear los precios únicos
                for price_data in all_prices_data:
                    locality_id = price_data.get('locality_id')
                    price_value = price_data.get('price')
                    
                    if not locality_id or price_value is None:
                        continue
                    
                    # Verificar que la localidad existe
                    locality = Locality.query.get(locality_id)
                    if not locality:
                        continue
                    
                    # Crear el precio (no verificamos existing_price porque estamos en una nueva creación)
                    price = ProductPrice(
                        product_variant_id=variant.id,
                        locality_id=locality_id,
                        price=price_value
                    )
                    db.session.add(price)
                
                # Hacer flush para obtener los IDs de los precios creados
                db.session.flush()
                
                # Ahora obtener los precios creados para el response
                prices_query = ProductPrice.query.filter_by(product_variant_id=variant.id).all()
                created_prices = [p.to_dict() for p in prices_query]
                
                created_variants.append({
                    **variant.to_dict(),
                    'prices': created_prices
                })
        
        db.session.commit()
        
        # Cargar imágenes si se proporcionaron
        if data.get('images'):
            from models.image import ProductImage
            # Eliminar imágenes existentes
            ProductImage.query.filter_by(product_id=product.id).delete()
            # Agregar nuevas imágenes
            for idx, img_data in enumerate(data['images']):
                image = ProductImage(
                    product_id=product.id,
                    image_url=img_data.get('image_url'),
                    alt_text=img_data.get('alt_text'),
                    position=img_data.get('position', idx)
                )
                db.session.add(image)
            db.session.commit()
        
        return jsonify({
            'success': True,
            'data': product.to_dict(include_images=True, include_variants=True)
        }), 200
        
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Error de integridad: El producto CRM ya está vinculado'
        }), 400
    except Exception as e:
        db.session.rollback()
        error_trace = traceback.format_exc()
        print(f"Error en complete_crm_product: {error_trace}")
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': error_trace if app.config.get('DEBUG') else None
        }), 500

@crm_products_bp.route('/admin/crm-combos', methods=['GET'])
@admin_required
def list_crm_combos():
    """
    Listar combos del CRM
    
    Query parameters:
    - search: término de búsqueda (busca en ID CRM, descripción, alt_description, product_name)
    - page: número de página (default: 1)
    - per_page: items por página (default: 20, max: 100)
    """
    try:
        search = request.args.get('search', '').strip()
        
        # Paginación
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        offset = (page - 1) * per_page
        
        # Construir query base para datos
        query_base = """
            SELECT 
                cp.id,
                cp.crm_product_id,
                cp.combo,
                cp.is_active,
                cp.commission,
                cp.price_sale,
                cp.description,
                cp.alt_description,
                cp.crm_created_at,
                cp.crm_updated_at,
                p.id as product_id,
                p.name as product_name
            FROM crm_products cp
            LEFT JOIN products p ON p.crm_product_id = cp.crm_product_id
        """
        
        params = {}
        conditions = ["cp.combo = true"]
        
        # Búsqueda
        if search:
            search_conditions = [
                "CAST(cp.crm_product_id AS TEXT) ILIKE :search",
                "cp.description ILIKE :search",
                "cp.alt_description ILIKE :search",
                "p.name ILIKE :search"
            ]
            conditions.append(f"({' OR '.join(search_conditions)})")
            params['search'] = f'%{search}%'
        
        where_clause = " WHERE " + " AND ".join(conditions)
        query = query_base + where_clause
        
        # Query para conteo
        count_query = f"SELECT COUNT(*) FROM crm_products cp LEFT JOIN products p ON p.crm_product_id = cp.crm_product_id{where_clause}"
        
        # Contar total
        count_result = db.session.execute(text(count_query), params)
        total = count_result.scalar()
        
        # Agregar paginación y ordenamiento
        query += " ORDER BY cp.crm_product_id LIMIT :limit OFFSET :offset"
        params['limit'] = per_page
        params['offset'] = offset
        
        # Obtener datos
        result = db.session.execute(text(query), params)
        rows = result.fetchall()
        
        combos = []
        for row in rows:
            # Obtener items del combo
            items_query = """
                SELECT 
                    cpci.crm_item_product_id,
                    cpci.quantity,
                    cpci.item_description,
                    cp.description as item_name
                FROM crm_product_combo_items cpci
                JOIN crm_products cp ON cp.crm_product_id = cpci.crm_item_product_id
                WHERE cpci.crm_combo_product_id = :combo_id
            """
            items_result = db.session.execute(text(items_query), {'combo_id': row.crm_product_id})
            items = []
            for item_row in items_result:
                items.append({
                    'crm_product_id': item_row.crm_item_product_id,
                    'quantity': item_row.quantity,
                    'item_description': item_row.item_description,
                    'item_name': item_row.item_name
                })
            
            combos.append({
                'id': str(row.id),
                'crm_product_id': row.crm_product_id,
                'is_active': row.is_active,
                'commission': float(row.commission) if row.commission else None,
                'price_sale': float(row.price_sale) if row.price_sale else None,
                'description': row.description,
                'alt_description': row.alt_description,
                'crm_created_at': row.crm_created_at.isoformat() if row.crm_created_at else None,
                'crm_updated_at': row.crm_updated_at.isoformat() if row.crm_updated_at else None,
                'product_id': str(row.product_id) if row.product_id else None,
                'product_name': row.product_name,
                'is_completed': row.product_id is not None,
                'items': items
            })
        
        total_pages = (total + per_page - 1) // per_page
        
        return jsonify({
            'success': True,
            'data': combos,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            }
        }), 200
        
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Error en list_crm_combos: {error_trace}")
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': error_trace if app.config.get('DEBUG') else None
        }), 500

@crm_products_bp.route('/admin/crm-combos/<uuid:combo_id>', methods=['GET'])
@admin_required
def get_crm_combo(combo_id):
    """Obtener un combo por ID"""
    try:
        query = """
            SELECT 
                cp.id,
                cp.crm_product_id,
                cp.is_active,
                cp.commission,
                cp.price_sale,
                cp.description,
                cp.alt_description,
                cp.crm_created_at,
                cp.crm_updated_at,
                cp.raw,
                p.id as product_id
            FROM crm_products cp
            LEFT JOIN products p ON p.crm_product_id = cp.crm_product_id
            WHERE cp.id = :combo_id AND cp.combo = true
        """
        
        result = db.session.execute(text(query), {'combo_id': str(combo_id)})
        row = result.fetchone()
        
        if not row:
            return jsonify({
                'success': False,
                'error': 'Combo no encontrado'
            }), 404
        
        # Obtener items del combo
        items_query = """
            SELECT 
                cpci.crm_item_product_id,
                cpci.quantity,
                cpci.item_description,
                cp.description as item_name
            FROM crm_product_combo_items cpci
            JOIN crm_products cp ON cp.crm_product_id = cpci.crm_item_product_id
            WHERE cpci.crm_combo_product_id = :combo_id
        """
        items_result = db.session.execute(text(items_query), {'combo_id': row.crm_product_id})
        items = []
        for item_row in items_result:
            items.append({
                'crm_product_id': item_row.crm_item_product_id,
                'quantity': item_row.quantity,
                'item_description': item_row.item_description,
                'item_name': item_row.item_name
            })
        
        combo_data = {
            'id': str(row.id),
            'crm_product_id': row.crm_product_id,
            'is_active': row.is_active,
            'commission': float(row.commission) if row.commission else None,
            'price_sale': float(row.price_sale) if row.price_sale else None,
            'description': row.description,
            'alt_description': row.alt_description,
            'crm_created_at': row.crm_created_at.isoformat() if row.crm_created_at else None,
            'crm_updated_at': row.crm_updated_at.isoformat() if row.crm_updated_at else None,
            'product_id': str(row.product_id) if row.product_id else None,
            'is_completed': row.product_id is not None,
            'items': items,
            'raw': row.raw
        }
        
        # Si está completado, obtener datos del producto
        if row.product_id:
            product = Product.query.get(row.product_id)
            if product:
                combo_data['product'] = product.to_dict(include_images=True, include_variants=True)
        
        return jsonify({
            'success': True,
            'data': combo_data
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

