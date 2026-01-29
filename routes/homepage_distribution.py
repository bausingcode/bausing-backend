from flask import Blueprint, request, jsonify
from database import db
from models.homepage_distribution import HomepageProductDistribution
from models.product import Product
from routes.admin import admin_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
import uuid

homepage_distribution_bp = Blueprint('homepage_distribution', __name__)

def get_available_replacement_product(exclude_product_ids, section_products=None):
    """Obtiene un producto disponible (con stock) para reemplazar uno sin stock"""
    try:
        # Buscar productos activos con stock que no estén en la lista de excluidos
        from sqlalchemy import and_, or_
        from models.product import Product, check_crm_stock
        
        query = Product.query.filter(
            Product.is_active == True,
            Product.id.notin_(exclude_product_ids) if exclude_product_ids else True
        )
        
        # Si hay productos de la sección, preferir productos de la misma categoría
        if section_products:
            category_ids = [p.category_id for p in section_products if p and p.category_id]
            if category_ids:
                query = query.filter(Product.category_id.in_(category_ids))
        
        # Verificar stock en crm_products
        available_products = []
        for product in query.limit(100).all():
            if check_crm_stock(product.crm_product_id):
                available_products.append(product)
                if len(available_products) >= 10:  # Limitar búsqueda
                    break
        
        return available_products[0] if available_products else None
    except Exception as e:
        print(f"[ERROR] Error obteniendo producto de reemplazo: {e}")
        return None

@homepage_distribution_bp.route('/admin/homepage-distribution', methods=['GET'])
@admin_required
def get_homepage_distribution():
    """Obtener toda la distribución de productos en el inicio"""
    try:
        distributions = HomepageProductDistribution.query.order_by(
            HomepageProductDistribution.section,
            HomepageProductDistribution.position
        ).all()
        
        # Organizar por sección
        result = {
            'featured': [None] * 4,  # 4 productos destacados
            'discounts': [None] * 3,  # 3 productos en descuentazos
            'mattresses': [None] * 4,  # 4 productos "Nuestros Colchones"
            'complete_purchase': [None] * 4  # 4 productos "Completa tu compra"
        }
        
        for dist in distributions:
            if dist.section in result and dist.position < len(result[dist.section]):
                result[dist.section][dist.position] = dist.to_dict(include_product=True)
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@homepage_distribution_bp.route('/admin/homepage-distribution', methods=['POST'])
@admin_required
def set_homepage_distribution():
    """Establecer o actualizar un producto en una posición específica"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400
        
        section = data.get('section')
        position = data.get('position')
        product_id = data.get('product_id')
        
        # Validaciones
        valid_sections = ['featured', 'discounts', 'mattresses', 'complete_purchase']
        if section not in valid_sections:
            return jsonify({
                'success': False,
                'error': f'Sección inválida. Debe ser una de: {", ".join(valid_sections)}'
            }), 400
        
        # Validar posición según la sección
        max_positions = {
            'featured': 4,
            'discounts': 3,
            'mattresses': 4,
            'complete_purchase': 4
        }
        
        if position is None or position < 0 or position >= max_positions[section]:
            return jsonify({
                'success': False,
                'error': f'Posición inválida. Debe estar entre 0 y {max_positions[section] - 1}'
            }), 400
        
        # Si product_id es None, eliminar la distribución en esa posición
        if product_id is None:
            existing = HomepageProductDistribution.query.filter_by(
                section=section,
                position=position
            ).first()
            
            if existing:
                db.session.delete(existing)
                db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Producto eliminado de la distribución'
            }), 200
        
        # Validar que el producto existe
        try:
            product_uuid = uuid.UUID(product_id)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'ID de producto inválido'
            }), 400
        
        product = Product.query.get(product_uuid)
        if not product:
            return jsonify({
                'success': False,
                'error': 'Producto no encontrado'
            }), 404
        
        # Buscar si ya existe una distribución en esta posición
        existing = HomepageProductDistribution.query.filter_by(
            section=section,
            position=position
        ).first()
        
        if existing:
            # Actualizar
            existing.product_id = product_uuid
            db.session.commit()
            
            return jsonify({
                'success': True,
                'data': existing.to_dict(include_product=True),
                'message': 'Distribución actualizada'
            }), 200
        else:
            # Crear nueva
            new_distribution = HomepageProductDistribution(
                section=section,
                position=position,
                product_id=product_uuid
            )
            db.session.add(new_distribution)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'data': new_distribution.to_dict(include_product=True),
                'message': 'Distribución creada'
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

@homepage_distribution_bp.route('/homepage-distribution/quick', methods=['GET'])
def get_public_homepage_distribution_quick():
    """Obtener la distribución de productos rápidamente (sin precios ni promociones)"""
    try:
        # Usar eager loading solo para imágenes y categorías básicas
        from sqlalchemy.orm import joinedload
        distributions = HomepageProductDistribution.query.filter(
            HomepageProductDistribution.product_id.isnot(None)
        ).options(
            joinedload(HomepageProductDistribution.product).joinedload(Product.images),
            joinedload(HomepageProductDistribution.product).joinedload(Product.category),
            joinedload(HomepageProductDistribution.product).joinedload(Product.category_option),
            joinedload(HomepageProductDistribution.product).joinedload(Product.subcategory_associations)
        ).order_by(
            HomepageProductDistribution.section,
            HomepageProductDistribution.position
        ).all()
        
        # Organizar por sección - solo datos básicos, sin precios ni promociones
        result = {
            'featured': [],
            'discounts': [],
            'mattresses': [],
            'complete_purchase': []
        }
        
        # Track de productos usados para evitar duplicados al reemplazar
        used_product_ids = set()
        
        for dist in distributions:
            if dist.section in result and dist.product:
                product = dist.product
                
                # Verificar stock en crm_products
                from models.product import check_crm_stock
                has_stock = check_crm_stock(product.crm_product_id)
                
                # Si no tiene stock, buscar un reemplazo
                if not has_stock:
                    print(f"[DEBUG] Producto {product.id} (crm_product_id: {product.crm_product_id}) sin stock, buscando reemplazo...")
                    # Obtener productos ya usados en esta sección
                    section_used_ids = [item['product']['id'] for item in result[dist.section] if 'product' in item and 'id' in item['product']]
                    all_used_ids = list(used_product_ids) + section_used_ids
                    
                    replacement = get_available_replacement_product(all_used_ids, [p.product for p in distributions if p.section == dist.section and p.product])
                    
                    if replacement:
                        print(f"[DEBUG] Reemplazando producto {product.id} con {replacement.id}")
                        product = replacement
                    else:
                        print(f"[DEBUG] No se encontró reemplazo para producto {product.id}, omitiendo...")
                        continue  # Omitir este producto si no hay reemplazo
                
                # Agregar a productos usados
                used_product_ids.add(str(product.id))
                
                # Solo datos básicos, sin precios ni promociones para carga rápida
                product_dict = product.to_dict(
                    include_variants=False,
                    include_images=True,
                    include_promos=False,
                    locality_id=None,
                    precalculated_min_price=0.0,  # Placeholder
                    precalculated_max_price=0.0    # Placeholder
                )
                # Remover precios para que el frontend sepa que debe cargarlos después
                product_dict['min_price'] = None
                product_dict['max_price'] = None
                product_dict['price_range'] = None
                product_dict['promos'] = []
                
                result[dist.section].append({
                    'position': dist.position,
                    'product': product_dict
                })
        
        # Ordenar por posición y extraer solo los productos
        for section in result:
            result[section].sort(key=lambda x: x['position'])
            result[section] = [item['product'] for item in result[section]]
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@homepage_distribution_bp.route('/homepage-distribution/prices', methods=['POST'])
def get_products_prices():
    """Obtener precios y promociones para productos específicos"""
    try:
        data = request.get_json()
        product_ids = data.get('product_ids', [])
        locality_id = data.get('locality_id', None)
        
        if not product_ids:
            return jsonify({
                'success': True,
                'data': {}
            }), 200
        
        # Pre-cargar el catálogo
        from models.product import get_cordoba_capital_catalog_id
        from models.catalog import LocalityCatalog
        from models.product import ProductVariant, ProductVariantOption, ProductPrice, Product
        from models.promo import Promo, PromoApplicability
        from sqlalchemy import func
        from datetime import datetime
        import uuid as uuid_lib
        
        # Convertir product_ids a UUIDs
        product_uuids = []
        for pid in product_ids:
            try:
                product_uuids.append(uuid_lib.UUID(pid) if isinstance(pid, str) else pid)
            except:
                continue
        
        if not product_uuids:
            return jsonify({
                'success': True,
                'data': {}
            }), 200
        
        # Determinar el catalog_id a usar
        target_catalog_id = None
        if locality_id:
            try:
                locality_uuid = uuid_lib.UUID(locality_id) if isinstance(locality_id, str) else locality_id
                locality_catalog = LocalityCatalog.query.filter_by(locality_id=locality_uuid).first()
                if locality_catalog:
                    target_catalog_id = locality_catalog.catalog_id
            except:
                pass
        else:
            target_catalog_id = get_cordoba_capital_catalog_id()
        
        # Pre-calcular precios
        price_map = {}
        if target_catalog_id:
            price_results = db.session.query(
                ProductVariant.product_id,
                func.min(ProductPrice.price).label('min_price'),
                func.max(ProductPrice.price).label('max_price')
            ).join(
                ProductVariantOption, ProductVariantOption.product_variant_id == ProductVariant.id
            ).join(
                ProductPrice, ProductPrice.product_variant_id == ProductVariantOption.id
            ).filter(
                ProductVariant.product_id.in_(product_uuids),
                ProductPrice.catalog_id == target_catalog_id
            ).group_by(ProductVariant.product_id).all()
            
            for result in price_results:
                price_map[result.product_id] = {
                    'min': float(result.min_price) if result.min_price else 0.0,
                    'max': float(result.max_price) if result.max_price else 0.0
                }
        
        # Pre-calcular promociones
        promo_map = {}
        category_map = {}
        
        # Obtener categorías
        products_with_categories = db.session.query(
            Product.id, Product.category_id
        ).filter(Product.id.in_(product_uuids)).all()
        
        for p in products_with_categories:
            category_map[p.id] = p.category_id
        
        # Cargar promociones válidas
        from sqlalchemy.orm import joinedload
        now = datetime.utcnow()
        all_promo_applicabilities = PromoApplicability.query.join(
            Promo, PromoApplicability.promo_id == Promo.id
        ).filter(
            Promo.is_active == True,
            Promo.start_at <= now,
            Promo.end_at >= now
        ).options(
            joinedload(PromoApplicability.promo)
        ).all()
        
        # Organizar promociones por producto
        for app in all_promo_applicabilities:
            promo_dict = app.promo.to_dict() if app.promo and app.promo.is_valid() else None
            if not promo_dict:
                continue
            
            if app.applies_to == 'all':
                for pid in product_uuids:
                    if pid not in promo_map:
                        promo_map[pid] = []
                    if not any(p.get('id') == promo_dict.get('id') for p in promo_map[pid]):
                        promo_map[pid].append(promo_dict)
            elif app.applies_to == 'product' and app.product_id:
                if app.product_id in product_uuids:
                    if app.product_id not in promo_map:
                        promo_map[app.product_id] = []
                    if not any(p.get('id') == promo_dict.get('id') for p in promo_map[app.product_id]):
                        promo_map[app.product_id].append(promo_dict)
            elif app.applies_to == 'category' and app.category_id:
                for pid, cat_id in category_map.items():
                    if cat_id == app.category_id:
                        if pid not in promo_map:
                            promo_map[pid] = []
                        if not any(p.get('id') == promo_dict.get('id') for p in promo_map[pid]):
                            promo_map[pid].append(promo_dict)
        
        # Construir respuesta
        result = {}
        for pid in product_uuids:
            pid_str = str(pid)
            result[pid_str] = {
                'min_price': price_map.get(pid, {}).get('min', 0.0),
                'max_price': price_map.get(pid, {}).get('max', 0.0),
                'promos': promo_map.get(pid, [])
            }
            # Calcular price_range
            min_p = result[pid_str]['min_price']
            max_p = result[pid_str]['max_price']
            if min_p > 0 or max_p > 0:
                result[pid_str]['price_range'] = min_p if min_p == max_p else f"{min_p} - {max_p}"
            else:
                result[pid_str]['price_range'] = "0"
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@homepage_distribution_bp.route('/homepage-distribution', methods=['GET'])
def get_public_homepage_distribution():
    """Obtener la distribución de productos para la página pública (sin autenticación)"""
    try:
        # Pre-cargar el catálogo "Cordoba capital" para optimizar (si no hay locality_id)
        from models.product import get_cordoba_capital_catalog_id
        locality_id = request.args.get('locality_id', None)
        if not locality_id:
            # Pre-cargar el cache del catálogo por defecto
            get_cordoba_capital_catalog_id()
        
        # Usar eager loading para evitar N+1 queries - cargar todas las relaciones necesarias
        from sqlalchemy.orm import joinedload
        from models.product import ProductVariant, ProductVariantOption
        distributions = HomepageProductDistribution.query.filter(
            HomepageProductDistribution.product_id.isnot(None)
        ).options(
            joinedload(HomepageProductDistribution.product).joinedload(Product.images),
            joinedload(HomepageProductDistribution.product).joinedload(Product.variants).joinedload(ProductVariant.options),
            joinedload(HomepageProductDistribution.product).joinedload(Product.category),
            joinedload(HomepageProductDistribution.product).joinedload(Product.category_option),
            joinedload(HomepageProductDistribution.product).joinedload(Product.subcategory_associations)
        ).order_by(
            HomepageProductDistribution.section,
            HomepageProductDistribution.position
        ).all()
        
        # Pre-calcular precios y promociones para todos los productos de una vez (optimización)
        from models.product import get_cordoba_capital_catalog_id
        from models.catalog import LocalityCatalog
        from models.product import ProductVariant, ProductVariantOption, ProductPrice
        from models.promo import Promo, PromoApplicability
        from sqlalchemy import func
        from datetime import datetime
        import uuid as uuid_lib
        
        # Determinar el catalog_id a usar
        target_catalog_id = None
        if locality_id:
            try:
                locality_uuid = uuid_lib.UUID(locality_id) if isinstance(locality_id, str) else locality_id
                locality_catalog = LocalityCatalog.query.filter_by(locality_id=locality_uuid).first()
                if locality_catalog:
                    target_catalog_id = locality_catalog.catalog_id
            except:
                pass
        else:
            target_catalog_id = get_cordoba_capital_catalog_id()
        
        # Pre-calcular min/max prices para todos los productos
        product_ids = [dist.product.id for dist in distributions if dist.product]
        price_map = {}  # {product_id: {'min': float, 'max': float}}
        
        if product_ids and target_catalog_id:
            # Query optimizado: obtener min/max price por producto en una sola consulta
            price_results = db.session.query(
                ProductVariant.product_id,
                func.min(ProductPrice.price).label('min_price'),
                func.max(ProductPrice.price).label('max_price')
            ).join(
                ProductVariantOption, ProductVariantOption.product_variant_id == ProductVariant.id
            ).join(
                ProductPrice, ProductPrice.product_variant_id == ProductVariantOption.id
            ).filter(
                ProductVariant.product_id.in_(product_ids),
                ProductPrice.catalog_id == target_catalog_id
            ).group_by(ProductVariant.product_id).all()
            
            for result in price_results:
                price_map[result.product_id] = {
                    'min': float(result.min_price) if result.min_price else 0.0,
                    'max': float(result.max_price) if result.max_price else 0.0
                }
        
        # Pre-calcular promociones para todos los productos de una vez (optimización)
        promo_map = {}  # {product_id: [promo_dict, ...]}
        category_map = {}  # {product_id: category_id}
        
        if product_ids:
            # Obtener categorías de todos los productos
            products_with_categories = db.session.query(
                Product.id, Product.category_id
            ).filter(Product.id.in_(product_ids)).all()
            
            for p in products_with_categories:
                category_map[p.id] = p.category_id
            
            # Cargar todas las promociones válidas y sus aplicabilidades de una vez
            now = datetime.utcnow()
            all_promo_applicabilities = PromoApplicability.query.join(
                Promo, PromoApplicability.promo_id == Promo.id
            ).filter(
                Promo.is_active == True,
                Promo.start_at <= now,
                Promo.end_at >= now
            ).options(
                joinedload(PromoApplicability.promo)
            ).all()
            
            # Organizar promociones por producto
            for app in all_promo_applicabilities:
                promo_dict = app.promo.to_dict() if app.promo and app.promo.is_valid() else None
                if not promo_dict:
                    continue
                
                if app.applies_to == 'all':
                    # Aplicar a todos los productos
                    for pid in product_ids:
                        if pid not in promo_map:
                            promo_map[pid] = []
                        # Evitar duplicados comparando por ID
                        if not any(p.get('id') == promo_dict.get('id') for p in promo_map[pid]):
                            promo_map[pid].append(promo_dict)
                elif app.applies_to == 'product' and app.product_id:
                    # Aplicar a producto específico
                    if app.product_id in product_ids:
                        if app.product_id not in promo_map:
                            promo_map[app.product_id] = []
                        # Evitar duplicados comparando por ID
                        if not any(p.get('id') == promo_dict.get('id') for p in promo_map[app.product_id]):
                            promo_map[app.product_id].append(promo_dict)
                elif app.applies_to == 'category' and app.category_id:
                    # Aplicar a todos los productos de esta categoría
                    for pid, cat_id in category_map.items():
                        if cat_id == app.category_id:
                            if pid not in promo_map:
                                promo_map[pid] = []
                            # Evitar duplicados comparando por ID
                            if not any(p.get('id') == promo_dict.get('id') for p in promo_map[pid]):
                                promo_map[pid].append(promo_dict)
        
        # Organizar por sección
        result = {
            'featured': [],
            'discounts': [],
            'mattresses': [],
            'complete_purchase': []
        }
        
        # Track de productos usados para evitar duplicados al reemplazar
        used_product_ids = set()
        
        for dist in distributions:
            if dist.section in result and dist.product:
                product = dist.product
                
                # Verificar stock en crm_products
                from models.product import check_crm_stock
                has_stock = check_crm_stock(product.crm_product_id)
                
                # Si no tiene stock, buscar un reemplazo
                if not has_stock:
                    print(f"[DEBUG] Producto {product.id} (crm_product_id: {product.crm_product_id}) sin stock, buscando reemplazo...")
                    # Obtener productos ya usados en esta sección
                    section_used_ids = [item['product']['id'] for item in result[dist.section] if 'product' in item and 'id' in item['product']]
                    all_used_ids = list(used_product_ids) + section_used_ids
                    
                    replacement = get_available_replacement_product(all_used_ids, [p.product for p in distributions if p.section == dist.section and p.product])
                    
                    if replacement:
                        print(f"[DEBUG] Reemplazando producto {product.id} con {replacement.id}")
                        product = replacement
                        # Recalcular precios para el producto de reemplazo
                        if replacement.id in price_map:
                            precalc_min_price = price_map[replacement.id]['min']
                            precalc_max_price = price_map[replacement.id]['max']
                        else:
                            precalc_min_price = None
                            precalc_max_price = None
                    else:
                        print(f"[DEBUG] No se encontró reemplazo para producto {product.id}, omitiendo...")
                        continue  # Omitir este producto si no hay reemplazo
                else:
                    # Obtener precios pre-calculados si están disponibles
                    if product.id in price_map:
                        precalc_min_price = price_map[product.id]['min']
                        precalc_max_price = price_map[product.id]['max']
                    else:
                        precalc_min_price = None
                        precalc_max_price = None
                
                # Agregar a productos usados
                used_product_ids.add(str(product.id))
                
                # Usar precios y promociones pre-calculadas directamente en to_dict para evitar queries innecesarias
                product_dict = product.to_dict(
                    include_variants=False,
                    include_images=True,
                    include_promos=False,  # Deshabilitado porque las pre-calculamos
                    locality_id=locality_id,
                    precalculated_min_price=precalc_min_price,
                    precalculated_max_price=precalc_max_price
                )
                
                # Agregar promociones pre-calculadas
                if product.id in promo_map:
                    product_dict['promos'] = promo_map[product.id]
                else:
                    product_dict['promos'] = []
                
                result[dist.section].append({
                    'position': dist.position,
                    'product': product_dict
                })
        
        # Ordenar por posición y extraer solo los productos
        for section in result:
            result[section].sort(key=lambda x: x['position'])
            result[section] = [item['product'] for item in result[section]]
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
