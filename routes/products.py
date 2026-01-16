from flask import Blueprint, request, jsonify
from database import db
from models.product import Product, ProductVariant, ProductVariantOption, ProductPrice
from models.image import ProductImage
from models.category import Category
from models.locality import Locality
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, and_, func, text
from sqlalchemy.orm import joinedload
from routes.admin import admin_required

products_bp = Blueprint('products', __name__)

@products_bp.route('', methods=['GET'])
def get_products():
    """
    Obtener productos con búsqueda, filtros y paginación
    
    Query parameters:
    - search: búsqueda por nombre, descripción o SKU
    - category_id: filtrar por categoría
    - category_ids: múltiples categorías separadas por coma
    - is_active: filtrar por estado activo (true/false)
    - min_price: precio mínimo
    - max_price: precio máximo
    - locality_id: filtrar precios por localidad
    - in_stock: solo productos con stock (true/false)
    - sort: ordenamiento (name, price_asc, price_desc, created_at, created_at_desc)
    - page: número de página (default: 1)
    - per_page: items por página (default: 20, max: 100)
    - include_variants: incluir variantes (true/false)
    - include_images: incluir todas las imágenes (true/false)
    - include_promos: incluir promociones aplicables (true/false)
    """
    try:
        # Parámetros de búsqueda
        search = request.args.get('search', '').strip()
        category_id = request.args.get('category_id')
        category_ids = request.args.get('category_ids')  # Múltiples categorías separadas por coma
        is_active = request.args.get('is_active')
        min_price = request.args.get('min_price', type=float)
        max_price = request.args.get('max_price', type=float)
        locality_id = request.args.get('locality_id')
        in_stock = request.args.get('in_stock')
        sort = request.args.get('sort', 'created_at_desc')
        
        # Paginación
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        
        # Incluir relaciones
        include_variants = request.args.get('include_variants', 'false').lower() == 'true'
        include_images = request.args.get('include_images', 'false').lower() == 'true'
        include_promos = request.args.get('include_promos', 'false').lower() == 'true'
        
        # Construir query base
        query = Product.query.options(joinedload(Product.images))
        
        # Búsqueda por texto
        if search:
            search_filter = or_(
                Product.name.ilike(f'%{search}%'),
                Product.description.ilike(f'%{search}%'),
                Product.sku.ilike(f'%{search}%')
            )
            query = query.filter(search_filter)
        
        # Filtro por categoría única
        if category_id:
            query = query.filter_by(category_id=category_id)
        
        # Filtro por múltiples categorías
        if category_ids:
            cat_ids_list = [cat_id.strip() for cat_id in category_ids.split(',')]
            query = query.filter(Product.category_id.in_(cat_ids_list))
        
        # Filtro por estado activo
        if is_active is not None:
            query = query.filter_by(is_active=is_active.lower() == 'true')
        else:
            # Por defecto, solo productos activos para ecommerce
            query = query.filter_by(is_active=True)
        
        # Filtro por stock
        if in_stock is not None and in_stock.lower() == 'true':
            # Solo productos que tienen al menos una option con stock > 0
            query = query.join(ProductVariant).join(ProductVariantOption).filter(ProductVariantOption.stock > 0).distinct()
        
        # Filtro por precio
        if min_price is not None or max_price is not None or locality_id:
            # Necesitamos hacer join con variantes y precios
            query = query.join(ProductVariant).join(ProductPrice)
            
            if locality_id:
                query = query.filter(ProductPrice.locality_id == locality_id)
            
            if min_price is not None:
                query = query.filter(ProductPrice.price >= min_price)
            
            if max_price is not None:
                query = query.filter(ProductPrice.price <= max_price)
            
            query = query.distinct()
        
        # Ordenamiento
        if sort == 'name':
            query = query.order_by(Product.name.asc())
        elif sort == 'name_desc':
            query = query.order_by(Product.name.desc())
        elif sort == 'price_asc':
            if locality_id:
                # Ordenar por precio mínimo en la localidad específica
                subquery = db.session.query(
                    ProductPrice.product_variant_id,
                    func.min(ProductPrice.price).label('min_price')
                ).filter_by(locality_id=locality_id).group_by(ProductPrice.product_variant_id).subquery()
                
                query = query.join(ProductVariant).join(
                    subquery, ProductVariant.id == subquery.c.product_variant_id
                ).order_by(subquery.c.min_price.asc()).distinct()
            else:
                # Ordenar por precio mínimo general
                subquery = db.session.query(
                    ProductVariant.product_id,
                    func.min(ProductPrice.price).label('min_price')
                ).join(ProductPrice).group_by(ProductVariant.product_id).subquery()
                
                query = query.join(subquery, Product.id == subquery.c.product_id).order_by(
                    subquery.c.min_price.asc()
                )
        elif sort == 'price_desc':
            if locality_id:
                subquery = db.session.query(
                    ProductPrice.product_variant_id,
                    func.max(ProductPrice.price).label('max_price')
                ).filter_by(locality_id=locality_id).group_by(ProductPrice.product_variant_id).subquery()
                
                query = query.join(ProductVariant).join(
                    subquery, ProductVariant.id == subquery.c.product_variant_id
                ).order_by(subquery.c.max_price.desc()).distinct()
            else:
                subquery = db.session.query(
                    ProductVariant.product_id,
                    func.max(ProductPrice.price).label('max_price')
                ).join(ProductPrice).group_by(ProductVariant.product_id).subquery()
                
                query = query.join(subquery, Product.id == subquery.c.product_id).order_by(
                    subquery.c.max_price.desc()
                )
        elif sort == 'created_at':
            query = query.order_by(Product.created_at.asc())
        else:  # created_at_desc (default)
            query = query.order_by(Product.created_at.desc())
        
        # Paginación
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        products = pagination.items
        
        # Serializar productos
        products_data = []
        for product in products:
            try:
                product_dict = product.to_dict(
                    include_variants=include_variants,
                    include_images=include_images,
                    locality_id=locality_id,
                    include_promos=include_promos
                )
                products_data.append(product_dict)
            except Exception as e:
                # Log error but continue with other products
                print(f"Error serializing product {product.id}: {str(e)}")
                import traceback
                traceback.print_exc()
                continue
        
        return jsonify({
            'success': True,
            'data': {
                'items': products_data,
                'page': pagination.page,
                'per_page': pagination.per_page,
                'total': pagination.total,
                'total_pages': pagination.pages
            }
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@products_bp.route('/<uuid:product_id>', methods=['GET'])
def get_product(product_id):
    """
    Obtener un producto por ID con toda la información del ecommerce
    
    Query parameters:
    - include_variants: incluir variantes (default: true)
    - include_images: incluir todas las imágenes (default: true)
    - include_promos: incluir promociones aplicables (default: true)
    - locality_id: filtrar precios por localidad
    """
    try:
        include_variants = request.args.get('include_variants', 'true').lower() == 'true'
        include_images = request.args.get('include_images', 'true').lower() == 'true'
        include_promos = request.args.get('include_promos', 'true').lower() == 'true'
        locality_id = request.args.get('locality_id')
        
        product = Product.query.options(joinedload(Product.images)).get_or_404(product_id)
        
        # Verificar que el producto esté activo (para ecommerce público)
        # Si es admin, puede ver productos inactivos también
        # Por ahora, permitimos ver todos
        
        return jsonify({
            'success': True,
            'data': product.to_dict(
                include_variants=include_variants,
                include_images=include_images,
                locality_id=locality_id,
                include_promos=include_promos
            )
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

@products_bp.route('/<uuid:product_id>/combos', methods=['GET'])
def get_product_combos(product_id):
    """
    Obtener combos que contienen este producto
    Busca en crm_product_combo_items donde crm_item_product_id = crm_product_id del producto
    """
    try:
        product = Product.query.get_or_404(product_id)
        
        # Si el producto no tiene crm_product_id, no puede estar en combos
        if not product.crm_product_id:
            return jsonify({
                'success': True,
                'data': []
            }), 200
        
        # Buscar combos que contengan este producto
        query = """
            SELECT DISTINCT
                cp.id,
                cp.crm_product_id,
                cp.description,
                cp.alt_description,
                cp.price_sale,
                cp.is_active,
                p.id as product_id,
                p.name as product_name
            FROM crm_product_combo_items cpci
            JOIN crm_products cp ON cp.crm_product_id = cpci.crm_combo_product_id
            LEFT JOIN products p ON p.crm_product_id = cp.crm_product_id
            WHERE cpci.crm_item_product_id = :crm_product_id
            AND cp.combo = true
            AND cp.is_active = true
            ORDER BY cp.crm_product_id
        """
        
        result = db.session.execute(text(query), {'crm_product_id': product.crm_product_id})
        rows = result.fetchall()
        
        combos = []
        for row in rows:
            # Obtener items del combo
            items_query = """
                SELECT 
                    cpci.crm_item_product_id,
                    cpci.quantity,
                    cpci.item_description,
                    cp2.description as item_name
                FROM crm_product_combo_items cpci
                JOIN crm_products cp2 ON cp2.crm_product_id = cpci.crm_item_product_id
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
                'description': row.description,
                'alt_description': row.alt_description,
                'price_sale': float(row.price_sale) if row.price_sale else None,
                'is_active': row.is_active,
                'product_id': str(row.product_id) if row.product_id else None,
                'product_name': row.product_name,
                'is_completed': row.product_id is not None,
                'items': items
            }
            
            # Si el combo está completado, obtener más información del producto
            if row.product_id:
                combo_product = Product.query.get(row.product_id)
                if combo_product:
                    combo_data['product'] = combo_product.to_dict(
                        include_images=True,
                        include_variants=False,
                        include_promos=True
                    )
            
            combos.append(combo_data)
        
        return jsonify({
            'success': True,
            'data': combos
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@products_bp.route('', methods=['POST'])
@admin_required
def create_product():
    """Crear un nuevo producto"""
    try:
        data = request.get_json()
        
        if not data or not data.get('name'):
            return jsonify({
                'success': False,
                'error': 'El nombre es requerido'
            }), 400
        
        product = Product(
            name=data['name'],
            description=data.get('description'),
            sku=data.get('sku'),
            category_id=data.get('category_id'),
            is_active=data.get('is_active', True)
        )
        
        db.session.add(product)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': product.to_dict()
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

@products_bp.route('/complete', methods=['POST'])
@admin_required
def create_complete_product():
    """
    Endpoint para crear un producto completo desde el admin panel.
    Incluye: producto, variantes, stock y precios por localidad en una sola operación.
    
    Body esperado:
    {
        "name": "Nombre del producto",
        "description": "Descripción",
        "sku": "SKU123",
        "category_id": "uuid-categoria",
        "subcategory_id": "uuid-subcategoria",  # opcional
        "is_active": true,
        "variants": [
            {
                "stock": 10,
                "prices": [
                    {
                        "locality_id": "uuid-localidad",
                        "price": 2999.99
                    }
                ]
            }
        ]
    }
    """
    try:
        data = request.get_json()
        
        if not data or not data.get('name'):
            return jsonify({
                'success': False,
                'error': 'El nombre del producto es requerido'
            }), 400
        
        # Determinar category_id (usar subcategory_id si existe, sino category_id)
        category_id = data.get('subcategory_id') or data.get('category_id')
        
        if not category_id:
            return jsonify({
                'success': False,
                'error': 'category_id o subcategory_id es requerido'
            }), 400
        
        # Verificar que la categoría existe
        category = Category.query.get(category_id)
        if not category:
            return jsonify({
                'success': False,
                'error': 'La categoría especificada no existe'
            }), 400
        
        # Crear el producto
        product = Product(
            name=data['name'],
            description=data.get('description'),
            sku=data.get('sku'),
            category_id=category_id,
            is_active=data.get('is_active', True)
        )
        
        db.session.add(product)
        db.session.flush()  # Para obtener el ID del producto
        
        # Crear variantes con sus precios
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
        
        return jsonify({
            'success': True,
            'data': {
                **product.to_dict(),
                'variants': created_variants
            }
        }), 201
        
    except IntegrityError as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': 'Error de integridad: ' + str(e)
        }), 400
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@products_bp.route('/<uuid:product_id>', methods=['PUT'])
@admin_required
def update_product(product_id):
    """Actualizar un producto"""
    try:
        product = Product.query.get_or_404(product_id)
        data = request.get_json()
        
        if 'name' in data:
            product.name = data['name']
        if 'description' in data:
            product.description = data.get('description')
        if 'sku' in data:
            product.sku = data.get('sku')
        if 'category_id' in data:
            product.category_id = data.get('category_id')
        if 'is_active' in data:
            product.is_active = data.get('is_active')
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': product.to_dict()
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

@products_bp.route('/<uuid:product_id>', methods=['DELETE'])
@admin_required
def delete_product(product_id):
    """Eliminar un producto"""
    try:
        product = Product.query.get_or_404(product_id)
        
        db.session.delete(product)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Producto eliminado correctamente'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@products_bp.route('/<uuid:product_id>/toggle-active', methods=['PATCH'])
@admin_required
def toggle_product_active(product_id):
    """Activar/desactivar un producto"""
    try:
        product = Product.query.get_or_404(product_id)
        product.is_active = not product.is_active
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': product.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@products_bp.route('/<uuid:product_id>/related', methods=['GET'])
def get_related_products(product_id):
    """
    Obtener productos relacionados (misma categoría)
    
    Query parameters:
    - limit: cantidad de productos relacionados (default: 4)
    - locality_id: filtrar precios por localidad
    """
    try:
        limit = min(request.args.get('limit', 4, type=int), 20)
        locality_id = request.args.get('locality_id')
        
        product = Product.query.get_or_404(product_id)
        
        # Buscar productos de la misma categoría, excluyendo el producto actual
        query = Product.query.filter(
            Product.category_id == product.category_id,
            Product.id != product_id,
            Product.is_active == True
        ).options(joinedload(Product.images))
        
        # Solo productos con stock (en options)
        query = query.join(ProductVariant).join(ProductVariantOption).filter(ProductVariantOption.stock > 0).distinct()
        
        related_products = query.limit(limit).all()
        
        return jsonify({
            'success': True,
            'data': [
                p.to_dict(
                    include_variants=False,
                    include_images=True,
                    locality_id=locality_id,
                    include_promos=True
                ) for p in related_products
            ]
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@products_bp.route('/featured', methods=['GET'])
def get_featured_products():
    """
    Obtener productos destacados (más recientes con stock)
    
    Query parameters:
    - limit: cantidad de productos (default: 8)
    - locality_id: filtrar precios por localidad
    """
    try:
        limit = min(request.args.get('limit', 8, type=int), 50)
        locality_id = request.args.get('locality_id')
        
        query = Product.query.filter(
            Product.is_active == True
        ).options(joinedload(Product.images))
        
        # Solo productos con stock (en options)
        query = query.join(ProductVariant).join(ProductVariantOption).filter(ProductVariantOption.stock > 0).distinct()
        
        # Ordenar por fecha de creación (más recientes primero)
        query = query.order_by(Product.created_at.desc())
        
        featured_products = query.limit(limit).all()
        
        return jsonify({
            'success': True,
            'data': [
                p.to_dict(
                    include_variants=False,
                    include_images=True,
                    locality_id=locality_id,
                    include_promos=True
                ) for p in featured_products
            ]
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@products_bp.route('/search-suggestions', methods=['GET'])
def get_search_suggestions():
    """
    Obtener sugerencias de búsqueda basadas en el término de búsqueda
    
    Query parameters:
    - q: término de búsqueda (requerido)
    - limit: cantidad de sugerencias (default: 5)
    """
    try:
        search_term = request.args.get('q', '').strip()
        limit = min(request.args.get('limit', 5, type=int), 10)
        
        if not search_term:
            return jsonify({
                'success': False,
                'error': 'El parámetro "q" es requerido'
            }), 400
        
        # Buscar productos que coincidan con el término
        products = Product.query.filter(
            Product.is_active == True,
            or_(
                Product.name.ilike(f'%{search_term}%'),
                Product.sku.ilike(f'%{search_term}%')
            )
        ).limit(limit).all()
        
        suggestions = [
            {
                'id': str(p.id),
                'name': p.name,
                'sku': p.sku,
                'main_image': p.get_main_image()
            }
            for p in products
        ]
        
        return jsonify({
            'success': True,
            'data': suggestions
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@products_bp.route('/price-range', methods=['GET'])
def get_price_range():
    """
    Obtener el rango de precios de todos los productos activos
    
    Query parameters:
    - locality_id: filtrar por localidad específica
    """
    try:
        locality_id = request.args.get('locality_id')
        
        if locality_id:
            # Precios filtrados por localidad
            result = db.session.query(
                func.min(ProductPrice.price).label('min_price'),
                func.max(ProductPrice.price).label('max_price')
            ).join(ProductVariant).join(Product).filter(
                ProductPrice.locality_id == locality_id,
                Product.is_active == True
            ).first()
        else:
            # Todos los precios
            result = db.session.query(
                func.min(ProductPrice.price).label('min_price'),
                func.max(ProductPrice.price).label('max_price')
            ).join(ProductVariant).join(Product).filter(
                Product.is_active == True
            ).first()
        
        if result and result.min_price:
            return jsonify({
                'success': True,
                'data': {
                    'min_price': float(result.min_price),
                    'max_price': float(result.max_price)
                }
            }), 200
        else:
            return jsonify({
                'success': True,
                'data': {
                    'min_price': None,
                    'max_price': None
                }
            }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

