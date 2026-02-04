from flask import Blueprint, request, jsonify, current_app
from database import db
from models.product import Product, ProductVariant, ProductVariantOption, ProductPrice
from models.locality import Locality
from models.catalog import Catalog
from models.category import Category, CategoryOption
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
        
        # Determinar qué producto usar
        product = None
        is_update = False
        
        if existing_product_id:
            # Hay un producto existente vinculado
            request_product_id = data.get('product_id')
            
            if request_product_id:
                # Si se proporciona product_id, debe coincidir con el existente
                if str(existing_product_id) != str(request_product_id):
                    return jsonify({
                        'success': False,
                        'error': 'El producto CRM ya está vinculado a otro producto diferente'
                    }), 400
                product = Product.query.get(request_product_id)
            else:
                # Si no se proporciona, usar el existente (actualización automática)
                product = Product.query.get(existing_product_id)
            
            if not product:
                return jsonify({
                    'success': False,
                    'error': 'Producto no encontrado'
                }), 404
            
            is_update = True
        elif data.get('product_id'):
            # No hay producto vinculado pero se proporciona product_id (actualizar producto existente sin vincular)
            product = Product.query.get(data['product_id'])
            if not product:
                return jsonify({
                    'success': False,
                    'error': 'Producto no encontrado'
                }), 404
            is_update = True
        
        # Si hay producto, actualizarlo
        if product:
            # Excluir campos que son relaciones o que se manejan por separado
            excluded_fields = {
                'product_id', 'variants', 'images', 'category_option', 'subcategory_associations',
                'created_at', 'id', 'subcategories'  # Campos que no deben actualizarse desde el request
            }
            
            for key, value in data.items():
                # Solo asignar campos simples (no relaciones, no listas/dicts complejos)
                if (key not in excluded_fields and 
                    hasattr(product, key) and 
                    not isinstance(value, (list, dict)) and
                    not key.startswith('_')):
                    setattr(product, key, value)
            
            # Manejar category_id y category_option_id como UUIDs si están presentes
            if 'category_id' in data and data['category_id']:
                cat_id = data['category_id']
                if isinstance(cat_id, uuid.UUID):
                    product.category_id = cat_id
                else:
                    product.category_id = uuid.UUID(str(cat_id))
            if 'category_option_id' in data and data['category_option_id']:
                opt_id = data['category_option_id']
                if isinstance(opt_id, uuid.UUID):
                    product.category_option_id = opt_id
                else:
                    product.category_option_id = uuid.UUID(str(opt_id))
            
            # Vincular el CRM product_id si no está vinculado
            if not product.crm_product_id:
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
                category_id=(uuid.UUID(str(data['category_id'])) if not isinstance(data['category_id'], uuid.UUID) else data['category_id']) if data.get('category_id') else None,
                category_option_id=(uuid.UUID(str(data['category_option_id'])) if not isinstance(data['category_option_id'], uuid.UUID) else data['category_option_id']) if data.get('category_option_id') else None,
                is_combo=is_combo,
                is_active=data.get('is_active', True)
            )
            db.session.add(product)
        
        db.session.flush()  # Para obtener el ID del producto
        
        # Eliminar variantes existentes si es actualización
        if is_update:
            # Eliminar variants, options y precios (los precios se eliminan automáticamente por cascade)
            variants_to_delete = ProductVariant.query.filter_by(product_id=product.id).all()
            
            # Verificar si existe la columna product_variant_id en order_items
            # y filtrar las variantes que están referenciadas
            try:
                check_column_query = """
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'order_items' 
                    AND column_name = 'product_variant_id'
                """
                column_check = db.session.execute(text(check_column_query))
                has_variant_column = column_check.fetchone() is not None
            except Exception:
                has_variant_column = False
            
            for v in variants_to_delete:
                # Verificar si la variante está referenciada en order_items
                if has_variant_column:
                    check_ref_query = """
                        SELECT COUNT(*) 
                        FROM order_items 
                        WHERE product_variant_id = :variant_id
                    """
                    ref_count = db.session.execute(
                        text(check_ref_query), 
                        {'variant_id': str(v.id)}
                    ).scalar()
                    
                    if ref_count and ref_count > 0:
                        # Esta variante está referenciada, no la eliminamos
                        print(f"[WARNING] No se puede eliminar la variante {v.id} porque está referenciada en {ref_count} order_items")
                        continue
                
                # Eliminar opciones (los precios se eliminan automáticamente por cascade desde las opciones)
                options_to_delete = ProductVariantOption.query.filter_by(product_variant_id=v.id).all()
                for opt in options_to_delete:
                    # Los precios se eliminan automáticamente por cascade desde ProductVariantOption
                    db.session.delete(opt)
                db.session.delete(v)
            db.session.flush()
            
            # Manejar subcategorías si vienen en el request
            if 'subcategory_ids' in data and isinstance(data['subcategory_ids'], list):
                # Eliminar subcategorías existentes PRIMERO para evitar conflictos
                from models.product import ProductSubcategory
                existing_assocs = ProductSubcategory.query.filter_by(product_id=product.id).all()
                print(f"[DEBUG] Eliminando {len(existing_assocs)} asociaciones existentes de subcategorías")
                for assoc in existing_assocs:
                    db.session.delete(assoc)
                db.session.flush()
                
                # Crear nuevas subcategorías
                # Para cada subcategoría, crear un registro por cada opción seleccionada
                subcategories_to_create = []
                for subcat_item in data['subcategory_ids']:
                    # Puede ser un string (id) o un objeto con subcategory_id y category_option_id
                    if isinstance(subcat_item, dict):
                        subcat_id = subcat_item.get('subcategory_id') or subcat_item.get('id')
                    else:
                        subcat_id = subcat_item
                    
                    if subcat_id:
                        # Convertir a string si es UUID y luego a UUID para asegurar el formato correcto
                        subcat_id_str = str(subcat_id)
                        subcat_id_uuid = uuid.UUID(subcat_id_str) if subcat_id_str else None
                        
                        # Obtener TODAS las opciones seleccionadas para esta subcategoría
                        selected_opts = []
                        if 'subcategory_options' in data and isinstance(data['subcategory_options'], dict):
                            # Usar el string para buscar en el dict
                            selected_opts = data['subcategory_options'].get(subcat_id_str, [])
                            if not isinstance(selected_opts, list):
                                selected_opts = [selected_opts] if selected_opts else []
                        
                        # Si hay opciones seleccionadas, crear un registro por cada opción
                        if selected_opts and len(selected_opts) > 0:
                            subcat = Category.query.get(subcat_id_uuid)
                            if subcat:
                                for opt_value in selected_opts:
                                    # Buscar el ID de la opción por su valor
                                    option_obj = CategoryOption.query.filter_by(
                                        category_id=subcat_id_uuid,
                                        value=str(opt_value)
                                    ).first()
                                    
                                    if option_obj:
                                        # Crear la asociación (ya eliminamos todas las anteriores con flush)
                                        subcategory_assoc = ProductSubcategory(
                                            product_id=product.id,
                                            subcategory_id=subcat_id_uuid,
                                            category_option_id=option_obj.id
                                        )
                                        db.session.add(subcategory_assoc)
                                        print(f"[DEBUG] Creada asociación: producto={product.id}, subcategoría={subcat_id_uuid}, opción={option_obj.value} (id={option_obj.id})")
                                    else:
                                        print(f"[DEBUG] No se encontró opción con valor '{opt_value}' para subcategoría {subcat_id_uuid}")
                        else:
                            # Si no hay opciones, crear un registro sin opción (solo uno por subcategoría)
                            if subcat_id_uuid:
                                # Crear la asociación sin opción (ya eliminamos todas las anteriores con flush)
                                subcategory_assoc = ProductSubcategory(
                                    product_id=product.id,
                                    subcategory_id=subcat_id_uuid,
                                    category_option_id=None
                                )
                                db.session.add(subcategory_assoc)
                                print(f"[DEBUG] Creada asociación sin opción: producto={product.id}, subcategoría={subcat_id_uuid}")
                db.session.flush()
            
            # Si hay category_id que es una categoría padre, actualizarla
            # (las subcategorías ya se manejaron arriba)
            if 'category_id' in data and data['category_id']:
                # Verificar que no sea una subcategoría
                cat_id_val = data['category_id']
                cat_id_uuid = cat_id_val if isinstance(cat_id_val, uuid.UUID) else uuid.UUID(str(cat_id_val))
                category = Category.query.get(cat_id_uuid)
                if category and not category.parent_id:
                    product.category_id = cat_id_uuid
        
        variants_data = data.get('variants', [])
        
        # Si no hay variantes pero hay precios directos en el nivel del producto, crear variante default con opción
        if not variants_data or len(variants_data) == 0:
            # Verificar si hay precios directos en el nivel del producto
            direct_prices = data.get('prices', [])
            if direct_prices and len(direct_prices) > 0:
                # Crear una variante "default" con una opción default
                default_variant = ProductVariant(
                    product_id=product.id,
                    sku=None,  # Sin SKU para variante default
                    price=None
                )
                db.session.add(default_variant)
                db.session.flush()
                
                # Crear una opción default
                default_option = ProductVariantOption(
                    product_variant_id=default_variant.id,
                    name='Default',
                    stock=0
                )
                db.session.add(default_option)
                db.session.flush()
                
                # Crear los precios para la opción default
                # Aceptar tanto catalog_id como locality_id (compatibilidad hacia atrás)
                price_list = direct_prices if isinstance(direct_prices, list) else [{'catalog_id': k, 'price': v} for k, v in direct_prices.items() if v]
                for price_data in price_list:
                    catalog_id = price_data.get('catalog_id')
                    locality_id = price_data.get('locality_id')  # Compatibilidad hacia atrás
                    price_value = price_data.get('price')
                    
                    if not price_value or price_value is None:
                        continue
                    
                    # Preferir catalog_id, pero mantener compatibilidad con locality_id
                    if catalog_id:
                        catalog = Catalog.query.get(catalog_id)
                        if not catalog:
                            continue
                        price = ProductPrice(
                            product_variant_id=default_option.id,
                            catalog_id=catalog_id,
                            price=price_value
                        )
                    elif locality_id:
                        # Compatibilidad hacia atrás: usar locality_id
                        locality = Locality.query.get(locality_id)
                        if not locality:
                            continue
                        price = ProductPrice(
                            product_variant_id=default_option.id,
                            locality_id=locality_id,
                            price=price_value
                        )
                    else:
                        continue
                    
                    db.session.add(price)
                
                db.session.flush()
        elif len(variants_data) > 0:
            # Procesar variantes con atributos y opciones
            # Primero, agrupar todas las options por atributo
            variants_dict = {}  # {attr_name: {variant_obj, options: {attr_value: {stock, prices}}}}
            
            for idx, variant_data in enumerate(variants_data):
                attributes = variant_data.get('attributes', {})
                prices_data = variant_data.get('prices', {})  # Ahora viene como objeto {catalog_id: price} o {locality_id: price}
                # Convertir prices_data de objeto a array si es necesario
                if isinstance(prices_data, dict):
                    # Intentar detectar si son catalog_id o locality_id
                    prices_data = [{'catalog_id': k, 'price': v} if k else None for k, v in prices_data.items() if v and k]
                    prices_data = [p for p in prices_data if p]  # Filtrar None
                elif not isinstance(prices_data, list):
                    prices_data = []
                
                # Si no hay atributos pero hay precios, crear una variante default para esta variant_data
                if not attributes and prices_data:
                    default_variant = ProductVariant(
                        product_id=product.id,
                        sku=None,
                        price=None
                    )
                    db.session.add(default_variant)
                    db.session.flush()
                    
                    # Crear una opción default para esta variante
                    default_option = ProductVariantOption(
                        product_variant_id=default_variant.id,
                        name='Default',
                        stock=0
                    )
                    db.session.add(default_option)
                    db.session.flush()
                    
                    # Crear los precios para esta opción default
                    for price_data in prices_data:
                        catalog_id = price_data.get('catalog_id')
                        locality_id = price_data.get('locality_id')  # Compatibilidad hacia atrás
                        price_value = price_data.get('price')
                        
                        if not price_value or price_value is None:
                            continue
                        
                        # Preferir catalog_id, pero mantener compatibilidad con locality_id
                        if catalog_id:
                            catalog = Catalog.query.get(catalog_id)
                            if not catalog:
                                continue
                            price = ProductPrice(
                                product_variant_id=default_option.id,
                                catalog_id=catalog_id,
                                price=price_value
                            )
                        elif locality_id:
                            locality = Locality.query.get(locality_id)
                            if not locality:
                                continue
                            price = ProductPrice(
                                product_variant_id=default_option.id,
                                locality_id=locality_id,
                                price=price_value
                            )
                        else:
                            continue
                        
                        db.session.add(price)
                    
                    db.session.flush()
                    continue
                
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
                    
                    # Si no existe la option para este valor, crearla sin stock
                    if attr_value not in variants_dict[attr_name]['options']:
                        option = ProductVariantOption(
                            product_variant_id=variants_dict[attr_name]['variant'].id,
                            name=attr_value,  # Valor de la opción (ej: "M")
                            stock=0  # No guardamos stock en las opciones
                        )
                        db.session.add(option)
                        db.session.flush()
                        variants_dict[attr_name]['options'][attr_value] = {
                            'option': option,
                            'prices': prices_data.copy() if isinstance(prices_data, list) else []
                        }
                        
                        # Crear los precios para esta opción específica
                        if isinstance(prices_data, list):
                            for price_item in prices_data:
                                catalog_id = price_item.get('catalog_id')
                                locality_id = price_item.get('locality_id')  # Compatibilidad hacia atrás
                                price_value = price_item.get('price')
                                
                                if not price_value or price_value is None:
                                    continue
                                
                                # Preferir catalog_id, pero mantener compatibilidad con locality_id
                                if catalog_id:
                                    catalog = Catalog.query.get(catalog_id)
                                    if catalog:
                                        price = ProductPrice(
                                            product_variant_id=option.id,
                                            catalog_id=catalog_id,
                                            price=price_value
                                        )
                                        db.session.add(price)
                                elif locality_id:
                                    locality = Locality.query.get(locality_id)
                                    if locality:
                                        price = ProductPrice(
                                            product_variant_id=option.id,
                                            locality_id=locality_id,
                                            price=price_value
                                        )
                                        db.session.add(price)
                        elif isinstance(prices_data, dict):
                            # Si viene como objeto {catalog_id: price} o {locality_id: price}
                            for key, price_value in prices_data.items():
                                if not key or price_value is None:
                                    continue
                                
                                # Intentar como catalog_id primero
                                catalog = Catalog.query.get(key)
                                if catalog:
                                    price = ProductPrice(
                                        product_variant_id=option.id,
                                        catalog_id=key,
                                        price=price_value
                                    )
                                    db.session.add(price)
                                else:
                                    # Intentar como locality_id (compatibilidad)
                                    locality = Locality.query.get(key)
                                    if locality:
                                        price = ProductPrice(
                                            product_variant_id=option.id,
                                            locality_id=key,
                                            price=price_value
                                        )
                                        db.session.add(price)
            
            # Los precios ya se crearon al crear cada opción, ahora solo necesitamos preparar la respuesta
            created_variants = []
            for attr_name, variant_info in variants_dict.items():
                variant = variant_info['variant']
                
                # Recopilar todos los precios de todas las opciones de esta variante
                all_prices = []
                for option_data in variant_info['options'].values():
                    option = option_data['option']
                    # Los precios están asociados a la opción (product_variant_id apunta a la opción)
                    option_prices = ProductPrice.query.filter_by(product_variant_id=option.id).all()
                    all_prices.extend([p.to_dict() for p in option_prices])
                
                created_variants.append({
                    **variant.to_dict(include_options=True),
                    'prices': all_prices  # Mantener compatibilidad con la estructura anterior
                })
        
        db.session.commit()
        
        # Procesar imágenes (siempre, incluso si está vacío para eliminar todas)
        if 'images' in data:
            from models.image import ProductImage
            # Eliminar imágenes existentes
            ProductImage.query.filter_by(product_id=product.id).delete()
            # Agregar nuevas imágenes solo si hay imágenes en el array
            if data.get('images') and len(data['images']) > 0:
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
        error_str = str(e)
        error_msg = 'Error de integridad'
        
        # Detectar el tipo específico de error de integridad
        if 'crm_product_id' in error_str.lower() or 'unique' in error_str.lower():
            if 'crm_product_id' in error_str.lower():
                error_msg = 'El producto CRM ya está vinculado a otro producto'
            elif 'unique_product_subcategory_option' in error_str.lower():
                error_msg = 'Ya existe una combinación de subcategoría y opción para este producto'
            else:
                error_msg = f'Error de integridad: {error_str}'
        
        print(f"[ERROR] IntegrityError en complete_crm_product: {error_str}")
        print(f"[ERROR] Traceback completo: {traceback.format_exc()}")
        
        return jsonify({
            'success': False,
            'error': error_msg,
            'debug': error_str if current_app.config.get('DEBUG', False) else None
        }), 400
    except Exception as e:
        db.session.rollback()
        error_trace = traceback.format_exc()
        print(f"Error en complete_crm_product: {error_trace}")
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': error_trace if current_app.config.get('DEBUG', False) else None
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

