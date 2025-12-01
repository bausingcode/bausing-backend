from flask import Blueprint, request, jsonify
from database import db
from models.product import Product, ProductVariant, ProductPrice
from models.image import ProductImage
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import joinedload

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
            # Solo productos que tienen al menos una variante con stock > 0
            query = query.join(ProductVariant).filter(ProductVariant.stock > 0).distinct()
        
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
            product_dict = product.to_dict(
                include_variants=include_variants,
                include_images=include_images,
                locality_id=locality_id,
                include_promos=include_promos
            )
            products_data.append(product_dict)
        
        return jsonify({
            'success': True,
            'data': products_data,
            'pagination': {
                'page': pagination.page,
                'per_page': pagination.per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
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

@products_bp.route('', methods=['POST'])
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

@products_bp.route('/<uuid:product_id>', methods=['PUT'])
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
        
        # Solo productos con stock
        query = query.join(ProductVariant).filter(ProductVariant.stock > 0).distinct()
        
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
        
        # Solo productos con stock
        query = query.join(ProductVariant).filter(ProductVariant.stock > 0).distinct()
        
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

