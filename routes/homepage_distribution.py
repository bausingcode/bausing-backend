from flask import Blueprint, request, jsonify
from database import db
from models.homepage_distribution import HomepageProductDistribution
from models.product import Product
from routes.admin import admin_required
from sqlalchemy.exc import IntegrityError
import uuid

homepage_distribution_bp = Blueprint('homepage_distribution', __name__)

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
        
        # Usar eager loading para evitar N+1 queries
        from sqlalchemy.orm import joinedload
        distributions = HomepageProductDistribution.query.filter(
            HomepageProductDistribution.product_id.isnot(None)
        ).options(
            joinedload(HomepageProductDistribution.product).joinedload(Product.images),
            joinedload(HomepageProductDistribution.product).joinedload(Product.variants)
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
        
        for dist in distributions:
            if dist.section in result and dist.product:
                # Usar promociones pre-calculadas en lugar de calcularlas en to_dict
                product_dict = dist.product.to_dict(
                    include_variants=False,
                    include_images=True,
                    include_promos=False,  # Deshabilitado porque las pre-calculamos
                    locality_id=locality_id
                )
                
                # Sobrescribir con precios pre-calculados si están disponibles (más rápido)
                if dist.product.id in price_map:
                    product_dict['min_price'] = price_map[dist.product.id]['min']
                    product_dict['max_price'] = price_map[dist.product.id]['max']
                    if price_map[dist.product.id]['min'] > 0 or price_map[dist.product.id]['max'] > 0:
                        product_dict['price_range'] = price_map[dist.product.id]['min'] if price_map[dist.product.id]['min'] == price_map[dist.product.id]['max'] else f"{price_map[dist.product.id]['min']} - {price_map[dist.product.id]['max']}"
                    else:
                        product_dict['price_range'] = "0"
                
                # Agregar promociones pre-calculadas
                if dist.product.id in promo_map:
                    product_dict['promos'] = promo_map[dist.product.id]
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
