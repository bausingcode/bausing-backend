import logging
import re
import time
import unicodedata
from collections import defaultdict
from flask import Blueprint, request, jsonify
from database import db

logger = logging.getLogger(__name__)
from models.product import (
    Product,
    ProductVariant,
    ProductVariantOption,
    ProductPrice,
    ProductSubcategory,
    product_price_transfer_filter,
    product_price_card_filter,
    PRICE_KIND_TRANSFER,
    PRICE_KIND_CARD,
    ALLOWED_BASIC_PRODUCT_COLORS,
    ALLOWED_BASIC_PRODUCT_COLORS,
    normalize_basic_product_color,
)
from models.image import ProductImage
from models.category import Category
from models.locality import Locality
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, and_, func, not_, text, bindparam, literal
from sqlalchemy.orm import joinedload, selectinload, aliased
from routes.admin import admin_required, verify_token

products_bp = Blueprint('products', __name__)

# pg_trgm (fuzzy); se prueba una sola vez por proceso
_trgm_available = None

# Reemplazos tras lower() para igualar términos con/sin tilde (sin depender de unaccent)
_FOLD_ACCENTS_SQL = (
    ("á", "a"), ("à", "a"), ("ä", "a"), ("â", "a"), ("ã", "a"), ("å", "a"),
    ("é", "e"), ("è", "e"), ("ë", "e"), ("ê", "e"),
    ("í", "i"), ("ì", "i"), ("ï", "i"), ("î", "i"),
    ("ó", "o"), ("ò", "o"), ("ö", "o"), ("ô", "o"), ("õ", "o"),
    ("ú", "u"), ("ù", "u"), ("ü", "u"), ("û", "u"),
    ("ñ", "n"),
    ("ç", "c"),
    ("ß", "ss"),
)


def _escape_ilike_pattern(s: str) -> str:
    """Escapa %, _ y \\ para usar con ILIKE ... ESCAPE '\\'."""
    if not s:
        return s
    return (
        s.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _py_fold(s: str) -> str:
    """Quita marcas diacríticas (NFD) y pasa a minúsculas (misma idea que unaccent)."""
    if not s:
        return ""
    nfd = unicodedata.normalize("NFD", s)
    stripped = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return stripped.lower()


def _sql_fold_accents(column):
    """Expresión SQL: lower + quitar tildes letra por letra (PostgreSQL)."""
    x = func.lower(column)
    for old, new in _FOLD_ACCENTS_SQL:
        x = func.replace(x, old, new)
    return x


def _trgm_works() -> bool:
    global _trgm_available
    if _trgm_available is not None:
        return _trgm_available
    try:
        row = db.session.execute(text("SELECT similarity('a', 'a')")).fetchone()
        _trgm_available = row is not None and row[0] is not None
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        _trgm_available = False
    return _trgm_available


def product_text_search_filter(search: str):
    """
    Búsqueda tolerante: ILIKE literal, ILIKE sin tildes (colchon ≈ colchón),
    nombre de categoría, y opcionalmente similarity (pg_trgm) para typos leves.
    Varias palabras: deben cumplirse todas (AND), cada una en nombre/desc/SKU/categoría.
    """
    q = (search or "").strip()
    if not q:
        return None
    words = [w for w in re.split(r"\s+", q) if w]
    if not words:
        return None

    use_trgm = _trgm_works()

    def one_word_clause(word: str):
        w_esc = _escape_ilike_pattern(word)
        pat = f"%{w_esc}%"
        w_fold = _py_fold(word)
        pat_fold = f"%{_escape_ilike_pattern(w_fold)}%"
        parts = []

        text_cols = (
            Product.name,
            Product.description,
            Product.technical_description,
            Product.sku,
        )
        for col in text_cols:
            parts.append(col.ilike(pat, escape="\\"))
            parts.append(_sql_fold_accents(col).like(pat_fold, escape="\\"))

        parts.append(Product.category.has(Category.name.ilike(pat, escape="\\")))
        parts.append(
            Product.category.has(_sql_fold_accents(Category.name).like(pat_fold, escape="\\"))
        )

        if use_trgm and len(w_fold) >= 4:
            parts.append(
                func.similarity(
                    _sql_fold_accents(func.coalesce(Product.name, literal(""))),
                    literal(w_fold),
                )
                > 0.34
            )
            parts.append(
                func.similarity(
                    _sql_fold_accents(func.coalesce(Product.sku, literal(""))),
                    literal(w_fold),
                )
                > 0.5
            )

        return or_(*parts)

    if len(words) == 1:
        return one_word_clause(words[0])
    return and_(*[one_word_clause(w) for w in words])


def _storefront_may_view_product_detail(product):
    """Tienda: solo productos activos. Admin (Bearer JWT) puede ver inactivos para edición/preview."""
    if getattr(product, "is_active", False):
        return True
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    try:
        token = auth.split(" ", 1)[1]
    except IndexError:
        return False
    return verify_token(token) is not None


def _batch_main_product_image_urls(product_ids):
    """Primera imagen por producto (listado) sin cargar todas las filas en memoria por ítem."""
    if not product_ids:
        return {}
    from models.image import ProductImage

    rn = (
        func.row_number()
        .over(
            partition_by=ProductImage.product_id,
            order_by=(
                ProductImage.position.asc().nulls_last(),
                ProductImage.created_at.asc(),
            ),
        )
        .label("rn")
    )
    subq = (
        db.session.query(ProductImage.product_id, ProductImage.image_url, rn).filter(
            ProductImage.product_id.in_(product_ids)
        )
    ).subquery()
    rows = (
        db.session.query(subq.c.product_id, subq.c.image_url)
        .filter(subq.c.rn == 1)
        .all()
    )
    out = {}
    for pid, url in rows:
        if url and str(url).strip():
            out[pid] = str(url).strip()
    return out


def _descendant_category_ids_including_root(root_id):
    """
    Raíz + todas las subcategorías. Una sola query a `categories` y recorrido en memoria.
    Sustituye recursión con N round-trips (Category.query por nivel).
    """
    from models.category import Category

    try:
        rows = db.session.query(Category.id, Category.parent_id).all()
    except Exception:
        return [root_id]
    by_parent = defaultdict(list)
    for cid, pid in rows:
        if pid is not None:
            by_parent[pid].append(cid)
    out = []
    stack = [root_id]
    seen = set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        out.append(cur)
        for ch in by_parent.get(cur, ()):
            stack.append(ch)
    return out if out else [root_id]


def _build_promo_map_for_product_ids(product_ids, category_id_by_product=None):
    """Pre-calculates applicable promos for many products; solo applicability relevante (no toda la tabla)."""
    promo_map = {}
    if not product_ids:
        return promo_map
    from models.promo import Promo, PromoApplicability
    from datetime import datetime

    if category_id_by_product is None:
        category_id_by_product = {
            row.id: row.category_id
            for row in db.session.query(Product.id, Product.category_id).filter(
                Product.id.in_(product_ids)
            ).all()
        }

    category_map = category_id_by_product
    now = datetime.utcnow()
    unique_category_ids = list({cid for cid in category_map.values() if cid is not None})

    applicability_conds = [
        PromoApplicability.applies_to == "all",
        and_(
            PromoApplicability.applies_to == "product",
            PromoApplicability.product_id.in_(product_ids),
        ),
    ]
    if unique_category_ids:
        applicability_conds.append(
            and_(
                PromoApplicability.applies_to == "category",
                PromoApplicability.category_id.in_(unique_category_ids),
            )
        )

    all_promo_applicabilities = (
        PromoApplicability.query.join(Promo, PromoApplicability.promo_id == Promo.id)
        .filter(
            Promo.is_active == True,
            Promo.start_at <= now,
            Promo.end_at >= now,
            or_(*applicability_conds),
        )
        .options(joinedload(PromoApplicability.promo))
        .all()
    )

    promos_for_all = []
    for app in all_promo_applicabilities:
        promo_dict = app.promo.to_dict() if app.promo and app.promo.is_valid() else None
        if not promo_dict:
            continue

        if app.applies_to == "all":
            promos_for_all.append(promo_dict)
        elif app.applies_to == "product" and app.product_id:
            if app.product_id in product_ids:
                promo_map.setdefault(app.product_id, [])
                if not any(p.get("id") == promo_dict.get("id") for p in promo_map[app.product_id]):
                    promo_map[app.product_id].append(promo_dict)
        elif app.applies_to == "category" and app.category_id:
            for pid, cat_id in category_map.items():
                if cat_id == app.category_id:
                    promo_map.setdefault(pid, [])
                    if not any(p.get("id") == promo_dict.get("id") for p in promo_map[pid]):
                        promo_map[pid].append(promo_dict)

    if promos_for_all:
        for pid in product_ids:
            lst = promo_map.setdefault(pid, [])
            seen = {p.get("id") for p in lst if p.get("id") is not None}
            for pdict in promos_for_all:
                iid = pdict.get("id")
                if iid is None:
                    lst.append(pdict)
                elif iid not in seen:
                    lst.append(pdict)
                    seen.add(iid)

    return promo_map


def _filling_type_slugs_or_condition(slugs):
    """
    OR entre slugs de Tecnología del catálogo (resortes-biconicos, espuma, etc.).
    Usa filling_type y CategoryOption.value de la opción principal del producto.
    """
    if not slugs:
        return None
    from models.category import CategoryOption

    b = func.lower(
        func.concat(
            func.coalesce(Product.filling_type, literal("")),
            literal(" "),
            func.coalesce(CategoryOption.value, literal("")),
        )
    )
    ors = []
    for raw in slugs:
        s = (raw or "").strip().lower().replace("_", "-")
        if s == "resortes-biconicos":
            ors.append(or_(b.like("%bicon%"), b.like("%bicón%")))
        elif s == "resortes-pocket":
            ors.append(b.like("%pocket%"))
        elif s in ("espuma-de-alta-densidad", "espuma-alta-densidad"):
            ors.append(
                and_(
                    b.like("%espuma%"),
                    b.like("%alta%"),
                    or_(b.like("%dens%"), b.like("%densi%")),
                )
            )
        elif s == "espuma":
            ors.append(
                and_(
                    b.like("%espuma%"),
                    not_(
                        and_(
                            b.like("%alta%"),
                            or_(b.like("%dens%"), b.like("%densi%")),
                        )
                    ),
                )
            )
    if not ors:
        return None
    if len(ors) == 1:
        return ors[0]
    return or_(*ors)


@products_bp.route('/basic-color-facets', methods=['GET'])
def get_basic_color_facets():
    """
    Lista corta de colores básicos presentes en productos de la categoría (raíz + descendientes).
    Query única DISTINCT; público (catálogo).
    Query: category_id (UUID categoría actual del listado — puede ser subcategoría).
    """
    try:
        category_id = request.args.get('category_id', '').strip()
        if not category_id:
            return jsonify({'success': False, 'error': 'category_id es requerido'}), 400
        import uuid as uuid_lib

        category_uuid = (
            uuid_lib.UUID(category_id) if isinstance(category_id, str) else category_id
        )

        cat_ids = _descendant_category_ids_including_root(category_uuid)
        if not cat_ids:
            return jsonify({'success': True, 'data': {'basic_colors': []}})

        rows = (
            db.session.query(Product.basic_color)
            .filter(
                Product.category_id.in_(cat_ids),
                Product.is_active.is_(True),
                Product.crm_product_id.isnot(None),
                Product.basic_color.in_(ALLOWED_BASIC_PRODUCT_COLORS),
            )
            .distinct()
            .all()
        )
        found = [r[0] for r in rows if r[0]]
        order = ['negro', 'beige', 'gris', 'blanco']
        idx = {c: i for i, c in enumerate(order)}
        basic_colors = sorted(found, key=lambda x: idx.get(x, 99))
        resp = jsonify({'success': True, 'data': {'basic_colors': basic_colors}})
        resp.headers['Cache-Control'] = 'public, max-age=60'
        return resp
    except Exception as e:
        logger.warning("basic-color-facets: %s", e)
        return jsonify({'success': True, 'data': {'basic_colors': []}})


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
    - require_crm_product_id: si true, solo productos vinculados a CRM (crm_product_id IS NOT NULL). Recomendado para vitrina/catálogo.
    - filling_type_slugs: slugs de Tecnología separados por coma (resortes-biconicos,espuma,espuma-de-alta-densidad,resortes-pocket); filtra por filling_type y opción de categoría principal.
    - subcategory_ids: UUIDs de filas de categoría (hijos) separados por coma; productos con asociación en product_subcategories (OR).
    - basic_colors: valores canónicos separados por coma (negro,beige,gris,blanco); productos cuyo basic_color está en la lista (OR).
    - product_ids: UUIDs separados por coma (máx. 12).

    Cada ítem incluye has_crm_stock (bool): false si el CRM marca el producto sin stock; la vitrina puede listarlo para mostrar etiqueta y deshabilitar compra en el frontend.
    """
    _catalog_t0 = time.perf_counter()
    _catalog_qs = (request.query_string or b'').decode('utf-8', errors='replace')
    logger.info("[catalog] GET /products start qs=%s", _catalog_qs)
    try:
        # Pre-cargar el catálogo "Cordoba capital" para optimizar (si no hay locality_id)
        from models.product import get_cordoba_capital_catalog_id
        from models.catalog import LocalityCatalog
        locality_id = request.args.get('locality_id')
        cached_locality_catalog = None
        if locality_id:
            try:
                import uuid as _uuid
                _lu = _uuid.UUID(locality_id) if isinstance(locality_id, str) else locality_id
                cached_locality_catalog = LocalityCatalog.query.filter_by(locality_id=_lu).first()
            except Exception:
                pass
        if not locality_id:
            get_cordoba_capital_catalog_id()
        
        # Parámetros de búsqueda
        search = request.args.get('search', '').strip()
        category_id = request.args.get('category_id')
        category_ids = request.args.get('category_ids')  # Múltiples categorías separadas por coma
        is_active = request.args.get('is_active')
        min_price = request.args.get('min_price', type=float)
        max_price = request.args.get('max_price', type=float)
        in_stock = request.args.get('in_stock')
        sort = request.args.get('sort', 'created_at_desc')
        
        # Paginación
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        
        # Incluir relaciones
        include_variants = request.args.get('include_variants', 'false').lower() == 'true'
        include_images = request.args.get('include_images', 'false').lower() == 'true'
        include_promos = request.args.get('include_promos', 'false').lower() == 'true'
        
        # Construir query base (imágenes: solo joinedload si hace falta la galería completa)
        # selectinload en subcategorías: evita multiplicar filas en el SELECT principal; COUNT/ OFFSET
        # son sobre productos reales (joinedload+LIMIT antes podía "gastar" el límite en filas duplicadas).
        from models.category import Category, CategoryOption
        eager = (
            joinedload(Product.category),
            joinedload(Product.category_option),
            selectinload(Product.subcategory_associations).selectinload(ProductSubcategory.subcategory),
            selectinload(Product.subcategory_associations).selectinload(ProductSubcategory.category_option),
        )
        if include_images:
            eager = (joinedload(Product.images),) + eager
        query = Product.query.options(*eager)

        product_ids_filter_list = None
        product_ids_raw = request.args.get('product_ids', '').strip()
        if product_ids_raw:
            _pid_parts = [x.strip() for x in product_ids_raw.split(',') if x.strip()]
            if len(_pid_parts) > 12:
                return jsonify({
                    'success': False,
                    'error': 'Máximo 12 valores en product_ids',
                }), 400
            try:
                import uuid as _uuid_pid
                product_ids_filter_list = [_uuid_pid.UUID(x) for x in _pid_parts]
            except Exception:
                return jsonify({
                    'success': False,
                    'error': 'product_ids: UUIDs inválidos',
                }), 400
            query = query.filter(Product.id.in_(product_ids_filter_list))

        ids_only_mode = product_ids_filter_list is not None
        
        # Búsqueda por texto (tildes, categoría, palabras múltiples, fuzzy si hay pg_trgm)
        if not ids_only_mode and search:
            search_filter = product_text_search_filter(search)
            if search_filter is not None:
                query = query.filter(search_filter)
        
        # Filtro por categoría única (incluyendo subcategorías)
        if not ids_only_mode and category_id:
            # Obtener todas las subcategorías (hijas) de esta categoría
            try:
                import uuid as uuid_lib
                category_uuid = uuid_lib.UUID(category_id) if isinstance(category_id, str) else category_id
                
                # Verificar que la categoría existe
                main_category = Category.query.get(category_uuid)
                if not main_category:
                    query = query.filter_by(category_id=category_id)  # Filtrar por ID inexistente (devolverá 0)
                else:
                    all_category_ids = _descendant_category_ids_including_root(category_uuid)
                    query = query.filter(Product.category_id.in_(all_category_ids))
            except Exception as e:
                import traceback
                # Fallback: filtrar solo por la categoría exacta
                query = query.filter_by(category_id=category_id)
        
        # Filtro por múltiples categorías
        if not ids_only_mode and category_ids:
            cat_ids_list = [cat_id.strip() for cat_id in category_ids.split(',')]
            query = query.filter(Product.category_id.in_(cat_ids_list))

        # Filtro por subcategoría(s) – tabla product_subcategories (mismo criterio que el catálogo)
        subcategory_ids_param = request.args.get('subcategory_ids', '').strip()
        if not ids_only_mode and subcategory_ids_param:
            sub_parts = [x.strip() for x in subcategory_ids_param.split(',') if x.strip()]
            if sub_parts:
                try:
                    import uuid as _uuid
                    sub_uuids = [
                        _uuid.UUID(x) if isinstance(x, str) else x
                        for x in sub_parts
                    ]
                    query = (
                        query.join(
                            ProductSubcategory,
                            Product.id == ProductSubcategory.product_id,
                        )
                        .filter(ProductSubcategory.subcategory_id.in_(sub_uuids))
                        .distinct()
                    )
                except Exception as e:
                    logger.warning("subcategory_ids filter skipped: %s", e)
        
        # Filtro por estado activo (Product.is_active: filter_by fallaría si el último join es otra entidad, ej. ProductSubcategory)
        if is_active is not None:
            query = query.filter(Product.is_active == (is_active.lower() == 'true'))
        elif not ids_only_mode:
            # Por defecto, solo productos activos para ecommerce (ids-only permite elegir explícitamente con is_active)
            query = query.filter(Product.is_active.is_(True))

        # Solo productos con vínculo CRM (vitrina / catálogo público)
        if request.args.get('require_crm_product_id', '').lower() in ('1', 'true', 'yes'):
            query = query.filter(Product.crm_product_id.isnot(None))

        # Tecnología (colchones): slugs canónicos separados por coma, mismo criterio que el catálogo en frontend
        filling_raw = request.args.get('filling_type_slugs', '').strip()
        if not ids_only_mode and filling_raw:
            slug_list = [x.strip() for x in filling_raw.split(',') if x.strip()]
            if slug_list:
                fcond = _filling_type_slugs_or_condition(slug_list)
                if fcond is not None:
                    query = query.outerjoin(
                        CategoryOption, Product.category_option_id == CategoryOption.id
                    )
                    query = query.filter(fcond)

        # Color básico (opcional en ficha): slugs separados por coma (OR)
        basic_colors_param = request.args.get('basic_colors', '').strip()
        if not ids_only_mode and basic_colors_param:
            parts = [
                normalize_basic_product_color(x.strip())
                for x in basic_colors_param.split(',')
            ]
            allowed_bc = [p for p in parts if p]
            if allowed_bc:
                query = query.filter(Product.basic_color.in_(allowed_bc))
        
        # Filtro por stock (stock en ProductVariantOption)
        if not ids_only_mode and in_stock is not None and in_stock.lower() == 'true':
            # Solo productos que tienen al menos una option con stock > 0
            query = query.join(ProductVariant).join(ProductVariantOption).filter(ProductVariantOption.stock > 0).distinct()
        
        # Filtro por precio (min/max) — solo aplica INNER JOIN cuando se filtra por rango de precios
        # El locality_id NO excluye productos: se usa solo para serializar los precios correctos
        if not ids_only_mode and (min_price is not None or max_price is not None):
            try:
                # Join correcto: Product -> ProductVariant -> ProductVariantOption -> ProductPrice
                query = query.join(
                    ProductVariant, ProductVariant.product_id == Product.id
                ).join(
                    ProductVariantOption, ProductVariantOption.product_variant_id == ProductVariant.id
                ).join(
                    ProductPrice, ProductPrice.product_variant_id == ProductVariantOption.id
                ).filter(product_price_transfer_filter())

                # Determinar catálogo para filtrar precios
                try:
                    import uuid as uuid_lib

                    if locality_id:
                        locality_uuid = uuid_lib.UUID(locality_id) if isinstance(locality_id, str) else locality_id
                        if cached_locality_catalog:
                            query = query.filter(
                                ProductPrice.catalog_id == cached_locality_catalog.catalog_id
                            )
                        else:
                            query = query.filter(ProductPrice.locality_id == locality_uuid)
                    else:
                        from models.product import get_cordoba_capital_catalog_id
                        cordoba_capital_catalog_id = get_cordoba_capital_catalog_id()
                        if cordoba_capital_catalog_id:
                            query = query.filter(ProductPrice.catalog_id == cordoba_capital_catalog_id)
                except (ValueError, TypeError) as e:
                    return jsonify({
                        'success': False,
                        'error': f'Formato de locality_id inválido: {locality_id}'
                    }), 400

                if min_price is not None:
                    query = query.filter(ProductPrice.price >= min_price)
                if max_price is not None:
                    query = query.filter(ProductPrice.price <= max_price)

                query = query.distinct()
            except Exception as e:
                import traceback
                return jsonify({
                    'success': False,
                    'error': f'Error al filtrar por precio: {str(e)}'
                }), 500
        
        # Ordenamiento
        if ids_only_mode:
            query = query.order_by(Product.created_at.desc())
        elif sort == 'name':
            query = query.order_by(Product.name.asc())
        elif sort == 'name_desc':
            query = query.order_by(Product.name.desc())
        elif sort == 'price_asc':
            if locality_id:
                # Ordenar por precio mínimo en la localidad específica
                # ProductPrice.product_variant_id apunta a ProductVariantOption.id
                try:
                    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
                    import uuid as uuid_lib
                    locality_uuid = uuid_lib.UUID(locality_id) if isinstance(locality_id, str) else locality_id
                    
                    locality_catalog = cached_locality_catalog
                    
                    subquery = db.session.query(
                        ProductVariantOption.product_variant_id,
                        func.min(ProductPrice.price).label('min_price')
                    ).join(
                        ProductPrice, ProductPrice.product_variant_id == ProductVariantOption.id
                    ).filter(product_price_transfer_filter())
                    if locality_catalog:
                        # Filtrar por catalog_id (nuevo sistema)
                        subquery = subquery.filter(ProductPrice.catalog_id == locality_catalog.catalog_id)
                    else:
                        # Compatibilidad hacia atrás: filtrar por locality_id
                        subquery = subquery.filter(ProductPrice.locality_id == locality_uuid)
                    subquery = subquery.group_by(ProductVariantOption.product_variant_id).subquery()
                    
                    # Incluir min_price en el SELECT: PostgreSQL exige que ORDER BY aparezca en el
                    # select list cuando se usa SELECT DISTINCT.
                    # Alias: si ya hay JOIN a product_variants (stock, rango de precio), un segundo
                    # .join(ProductVariant) es ambiguo; el alias fija el lado del FROM.
                    pv_for_price_sort = aliased(ProductVariant)
                    query = query.join(
                        pv_for_price_sort, Product.id == pv_for_price_sort.product_id
                    ).join(
                        subquery, pv_for_price_sort.id == subquery.c.product_variant_id
                    ).add_columns(subquery.c.min_price).order_by(
                        subquery.c.min_price.asc()
                    ).distinct()
                except (ValueError, TypeError) as e:
                    # Continuar sin ordenar por precio si hay error
                    query = query.order_by(Product.created_at.desc())
            else:
                # Ordenar por precio mínimo del catálogo "Cordoba capital" por defecto
                from models.product import get_cordoba_capital_catalog_id
                cordoba_capital_catalog_id = get_cordoba_capital_catalog_id()
                if cordoba_capital_catalog_id:
                    subquery = db.session.query(
                        ProductVariant.product_id,
                        func.min(ProductPrice.price).label('min_price')
                    ).join(ProductPrice).filter(
                        ProductPrice.catalog_id == cordoba_capital_catalog_id,
                        product_price_transfer_filter(),
                    ).group_by(ProductVariant.product_id).subquery()
                else:
                    # Si no existe el catálogo, ordenar por precio mínimo general
                    subquery = db.session.query(
                        ProductVariant.product_id,
                        func.min(ProductPrice.price).label('min_price')
                    ).join(ProductPrice).filter(product_price_transfer_filter()).group_by(ProductVariant.product_id).subquery()
                
                query = query.join(subquery, Product.id == subquery.c.product_id).add_columns(
                    subquery.c.min_price
                ).order_by(subquery.c.min_price.asc())
        elif sort == 'price_desc':
            if locality_id:
                # Ordenar por precio máximo en la localidad específica
                # ProductPrice.product_variant_id apunta a ProductVariantOption.id
                try:
                    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
                    import uuid as uuid_lib
                    locality_uuid = uuid_lib.UUID(locality_id) if isinstance(locality_id, str) else locality_id
                    
                    locality_catalog = cached_locality_catalog
                    
                    subquery = db.session.query(
                        ProductVariantOption.product_variant_id,
                        func.max(ProductPrice.price).label('max_price')
                    ).join(
                        ProductPrice, ProductPrice.product_variant_id == ProductVariantOption.id
                    ).filter(product_price_transfer_filter())
                    if locality_catalog:
                        # Filtrar por catalog_id (nuevo sistema)
                        subquery = subquery.filter(ProductPrice.catalog_id == locality_catalog.catalog_id)
                    else:
                        # Compatibilidad hacia atrás: filtrar por locality_id
                        subquery = subquery.filter(ProductPrice.locality_id == locality_uuid)
                    subquery = subquery.group_by(ProductVariantOption.product_variant_id).subquery()
                    
                    pv_for_price_sort = aliased(ProductVariant)
                    query = query.join(
                        pv_for_price_sort, Product.id == pv_for_price_sort.product_id
                    ).join(
                        subquery, pv_for_price_sort.id == subquery.c.product_variant_id
                    ).add_columns(subquery.c.max_price).order_by(
                        subquery.c.max_price.desc()
                    ).distinct()
                except (ValueError, TypeError) as e:
                    # Continuar sin ordenar por precio si hay error
                    query = query.order_by(Product.created_at.desc())
            else:
                # Ordenar por precio máximo del catálogo "Cordoba capital" por defecto
                from models.product import get_cordoba_capital_catalog_id
                cordoba_capital_catalog_id = get_cordoba_capital_catalog_id()
                if cordoba_capital_catalog_id:
                    subquery = db.session.query(
                        ProductVariant.product_id,
                        func.max(ProductPrice.price).label('max_price')
                    ).join(ProductPrice).filter(
                        ProductPrice.catalog_id == cordoba_capital_catalog_id,
                        product_price_transfer_filter(),
                    ).group_by(ProductVariant.product_id).subquery()
                else:
                    # Si no existe el catálogo, ordenar por precio máximo general
                    subquery = db.session.query(
                        ProductVariant.product_id,
                        func.max(ProductPrice.price).label('max_price')
                    ).join(ProductPrice).filter(product_price_transfer_filter()).group_by(ProductVariant.product_id).subquery()
                
                query = query.join(subquery, Product.id == subquery.c.product_id).add_columns(
                    subquery.c.max_price
                ).order_by(subquery.c.max_price.desc())
        elif sort == 'created_at':
            query = query.order_by(Product.created_at.asc())
        else:  # created_at_desc (default)
            query = query.order_by(Product.created_at.desc())
        
        # Paginación
        try:
            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            _raw_items = pagination.items
            # add_columns( precio agregado ) devuelve filas (Product, col); sino, modelos Product.
            products = [
                row[0] if not isinstance(row, Product) else row
                for row in _raw_items
            ]
            if product_ids_filter_list:
                _order_map = {str(u): i for i, u in enumerate(product_ids_filter_list)}
                products.sort(key=lambda p: _order_map.get(str(p.id), 999))
        except Exception as e:
            import traceback
            return jsonify({
                'success': False,
                'error': f'Error al paginar productos: {str(e)}'
            }), 500
        
        # Pre-calcular precios mínimos y máximos para todos los productos de una vez (optimización)
        from models.product import get_cordoba_capital_catalog_id
        import uuid as uuid_lib
        
        # Determinar el catalog_id a usar (misma fila localidad→catálogo que arriba)
        target_catalog_id = None
        if locality_id and cached_locality_catalog:
            target_catalog_id = cached_locality_catalog.catalog_id
        elif not locality_id:
            target_catalog_id = get_cordoba_capital_catalog_id()
        
        # Pre-calcular min/max prices y promociones para todos los productos de una vez (optimización)
        product_ids = [p.id for p in products]
        main_image_by_pid = (
            _batch_main_product_image_urls(product_ids)
            if product_ids and not include_images
            else {}
        )
        price_map = {}  # {product_id: {'min': float, 'max': float}}
        card_price_map = {}
        transfer_only_map = {}  # solo filas transfer/efectivo (para mostrar ambos precios en tienda)
        category_id_by_product = {p.id: p.category_id for p in products}
        promo_map = (
            _build_promo_map_for_product_ids(product_ids, category_id_by_product)
            if include_promos and product_ids
            else {}
        )
        
        if product_ids and target_catalog_id:
            # Tarjeta primero (precio de lista); si no hay filas card, usar transfer (legacy).
            card_results = db.session.query(
                ProductVariant.product_id,
                func.min(ProductPrice.price).label('min_price'),
                func.max(ProductPrice.price).label('max_price')
            ).join(
                ProductVariantOption, ProductVariantOption.product_variant_id == ProductVariant.id
            ).join(
                ProductPrice, ProductPrice.product_variant_id == ProductVariantOption.id
            ).filter(
                ProductVariant.product_id.in_(product_ids),
                ProductPrice.catalog_id == target_catalog_id,
                ProductPrice.price_kind == PRICE_KIND_CARD,
            ).group_by(ProductVariant.product_id).all()
            for result in card_results:
                slot = {
                    'min': float(result.min_price) if result.min_price else 0.0,
                    'max': float(result.max_price) if result.max_price else 0.0
                }
                price_map[result.product_id] = slot
                card_price_map[result.product_id] = slot

            transfer_results = db.session.query(
                ProductVariant.product_id,
                func.min(ProductPrice.price).label('min_price'),
                func.max(ProductPrice.price).label('max_price')
            ).join(
                ProductVariantOption, ProductVariantOption.product_variant_id == ProductVariant.id
            ).join(
                ProductPrice, ProductPrice.product_variant_id == ProductVariantOption.id
            ).filter(
                ProductVariant.product_id.in_(product_ids),
                ProductPrice.catalog_id == target_catalog_id,
                product_price_transfer_filter(),
            ).group_by(ProductVariant.product_id).all()
            for result in transfer_results:
                transfer_only_map[result.product_id] = {
                    'min': float(result.min_price) if result.min_price else 0.0,
                    'max': float(result.max_price) if result.max_price else 0.0
                }
                if result.product_id in price_map:
                    continue
                price_map[result.product_id] = {
                    'min': float(result.min_price) if result.min_price else 0.0,
                    'max': float(result.max_price) if result.max_price else 0.0
                }
        elif product_ids:
            # Si no hay catalog_id, buscar por locality_id o todos los precios
            if locality_id:
                try:
                    locality_uuid = uuid_lib.UUID(locality_id) if isinstance(locality_id, str) else locality_id
                    card_loc_results = db.session.query(
                        ProductVariant.product_id,
                        func.min(ProductPrice.price).label('min_price'),
                        func.max(ProductPrice.price).label('max_price')
                    ).join(
                        ProductVariantOption, ProductVariantOption.product_variant_id == ProductVariant.id
                    ).join(
                        ProductPrice, ProductPrice.product_variant_id == ProductVariantOption.id
                    ).filter(
                        ProductVariant.product_id.in_(product_ids),
                        ProductPrice.locality_id == locality_uuid,
                        ProductPrice.price_kind == PRICE_KIND_CARD,
                    ).group_by(ProductVariant.product_id).all()
                    for result in card_loc_results:
                        slot = {
                            'min': float(result.min_price) if result.min_price else 0.0,
                            'max': float(result.max_price) if result.max_price else 0.0
                        }
                        price_map[result.product_id] = slot
                        card_price_map[result.product_id] = slot

                    transfer_results = db.session.query(
                        ProductVariant.product_id,
                        func.min(ProductPrice.price).label('min_price'),
                        func.max(ProductPrice.price).label('max_price')
                    ).join(
                        ProductVariantOption, ProductVariantOption.product_variant_id == ProductVariant.id
                    ).join(
                        ProductPrice, ProductPrice.product_variant_id == ProductVariantOption.id
                    ).filter(
                        ProductVariant.product_id.in_(product_ids),
                        ProductPrice.locality_id == locality_uuid,
                        product_price_transfer_filter(),
                    ).group_by(ProductVariant.product_id).all()
                    for result in transfer_results:
                        transfer_only_map[result.product_id] = {
                            'min': float(result.min_price) if result.min_price else 0.0,
                            'max': float(result.max_price) if result.max_price else 0.0
                        }
                        if result.product_id in price_map:
                            continue
                        price_map[result.product_id] = {
                            'min': float(result.min_price) if result.min_price else 0.0,
                            'max': float(result.max_price) if result.max_price else 0.0
                        }
                except:
                    pass
        
        # Serializar productos
        from models.product import get_crm_stock_map, crm_id_has_stock

        _catalog_crm_ids = [p.crm_product_id for p in products if getattr(p, "crm_product_id", None)]
        _catalog_stock_map = get_crm_stock_map(_catalog_crm_ids)

        products_data = []
        for product in products:
            try:
                # Convertir locality_id a UUID si es string
                locality_uuid = None
                if locality_id:
                    try:
                        locality_uuid = uuid_lib.UUID(locality_id) if isinstance(locality_id, str) else locality_id
                    except (ValueError, TypeError) as e:
                        locality_uuid = None
                
                # Obtener precios pre-calculados si están disponibles
                precalc_min_price = None
                precalc_max_price = None
                if product.id in price_map:
                    precalc_min_price = price_map[product.id]['min']
                    precalc_max_price = price_map[product.id]['max']
                
                # Usar precios y promociones pre-calculados directamente en to_dict para evitar queries innecesarias
                product_dict = product.to_dict(
                    include_variants=include_variants,
                    include_images=include_images,
                    locality_id=str(locality_uuid) if locality_uuid else None,
                    include_promos=False,  # Deshabilitado porque las pre-calculamos
                    precalculated_min_price=precalc_min_price,
                    precalculated_max_price=precalc_max_price,
                    include_inventory=False,
                    precalculated_main_image=main_image_by_pid.get(product.id),
                )
                
                # Agregar promociones pre-calculadas
                if include_promos:
                    if product.id in promo_map:
                        product_dict['promos'] = promo_map[product.id]
                    else:
                        product_dict['promos'] = []

                tmin = product_dict.get('min_price') or 0
                tmax = product_dict.get('max_price') or 0
                cslot = card_price_map.get(product.id)
                if cslot and cslot.get('min', 0) > 0:
                    product_dict['min_card_price'] = cslot['min']
                    product_dict['max_card_price'] = cslot.get('max') or cslot['min']
                else:
                    product_dict['min_card_price'] = tmin
                    product_dict['max_card_price'] = tmax

                xslot = transfer_only_map.get(product.id)
                if xslot and xslot.get('min', 0) > 0:
                    product_dict['min_transfer_price'] = xslot['min']
                    product_dict['max_transfer_price'] = xslot.get('max') or xslot['min']

                product_dict['has_crm_stock'] = crm_id_has_stock(product.crm_product_id, _catalog_stock_map)

                products_data.append(product_dict)
            except Exception as e:
                # Log error but continue with other products
                import traceback
                continue

        _elapsed_ms = (time.perf_counter() - _catalog_t0) * 1000.0
        logger.info(
            "[catalog] GET /products ok page=%d/%d items=%d total=%d %.0fms",
            pagination.page,
            pagination.pages,
            len(products_data),
            pagination.total,
            _elapsed_ms,
        )
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
        _elapsed_ms = (time.perf_counter() - _catalog_t0) * 1000.0
        logger.exception(
            "[catalog] GET /products error after %.0fms qs=%s: %s",
            _elapsed_ms,
            _catalog_qs,
            e,
        )
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
    - include_all_variant_prices: si true, en cada opción se devuelven todas las filas de precio (todos los catálogos);
      si false (default), sin locality_id se filtra al catálogo Córdoba capital para la vitrina.
    """
    # Limpiar cualquier transacción abortada antes de comenzar
    try:
        db.session.rollback()
    except:
        pass
    
    try:
        include_variants = request.args.get('include_variants', 'true').lower() == 'true'
        include_images = request.args.get('include_images', 'true').lower() == 'true'
        include_promos = request.args.get('include_promos', 'true').lower() == 'true'
        locality_id = request.args.get('locality_id')
        # Incluir todas las filas de precio por catálogo/localidad (admin/edición; evita filtrar solo a Córdoba capital)
        include_all_variant_prices = request.args.get('include_all_variant_prices', 'false').lower() == 'true'

        import uuid as uuid_lib
        from models.catalog import LocalityCatalog
        from models.product import get_cordoba_capital_catalog_id, check_crm_stock

        locality_to_catalog = {}
        target_catalog_id = None
        locality_uuid = None
        if locality_id:
            try:
                locality_uuid = uuid_lib.UUID(locality_id) if isinstance(locality_id, str) else locality_id
                locality_catalog = LocalityCatalog.query.filter_by(locality_id=locality_uuid).first()
                if locality_catalog:
                    locality_to_catalog[str(locality_uuid)] = str(locality_catalog.catalog_id)
                    target_catalog_id = locality_catalog.catalog_id
            except Exception:
                pass
        else:
            target_catalog_id = get_cordoba_capital_catalog_id()

        product = Product.query.options(
            joinedload(Product.images),
            joinedload(Product.category),
            joinedload(Product.category_option),
            joinedload(Product.subcategory_associations).joinedload(ProductSubcategory.subcategory),
            joinedload(Product.subcategory_associations).joinedload(ProductSubcategory.category_option),
            joinedload(Product.variants)
            .joinedload(ProductVariant.options)
            .joinedload(ProductVariantOption.prices)
            .options(
                joinedload(ProductPrice.catalog),
                joinedload(ProductPrice.locality),
            ),
        ).get(product_id)

        if not product:
            return jsonify({
                'success': False,
                'error': f'Producto con ID {product_id} no encontrado'
            }), 404

        if not _storefront_may_view_product_detail(product):
            return jsonify({
                'success': False,
                'error': 'Producto no disponible'
            }), 404

        precalc_min_price = None
        precalc_max_price = None
        if target_catalog_id:
            price_row = (
                db.session.query(
                    func.min(ProductPrice.price).label('min_price'),
                    func.max(ProductPrice.price).label('max_price'),
                )
                .select_from(ProductVariant)
                .join(
                    ProductVariantOption,
                    ProductVariantOption.product_variant_id == ProductVariant.id,
                )
                .join(
                    ProductPrice,
                    ProductPrice.product_variant_id == ProductVariantOption.id,
                )
                .filter(
                    ProductVariant.product_id == product.id,
                    ProductPrice.catalog_id == target_catalog_id,
                    product_price_card_filter(),
                )
                .first()
            )
            if price_row is None or (
                price_row.min_price is None and price_row.max_price is None
            ):
                price_row = (
                    db.session.query(
                        func.min(ProductPrice.price).label('min_price'),
                        func.max(ProductPrice.price).label('max_price'),
                    )
                    .select_from(ProductVariant)
                    .join(
                        ProductVariantOption,
                        ProductVariantOption.product_variant_id == ProductVariant.id,
                    )
                    .join(
                        ProductPrice,
                        ProductPrice.product_variant_id == ProductVariantOption.id,
                    )
                    .filter(
                        ProductVariant.product_id == product.id,
                        ProductPrice.catalog_id == target_catalog_id,
                        product_price_transfer_filter(),
                    )
                    .first()
                )
            if price_row is not None and (
                price_row.min_price is not None or price_row.max_price is not None
            ):
                precalc_min_price = (
                    float(price_row.min_price) if price_row.min_price is not None else 0.0
                )
                precalc_max_price = (
                    float(price_row.max_price) if price_row.max_price is not None else 0.0
                )
        elif locality_uuid is not None:
            price_row = (
                db.session.query(
                    func.min(ProductPrice.price).label('min_price'),
                    func.max(ProductPrice.price).label('max_price'),
                )
                .select_from(ProductVariant)
                .join(
                    ProductVariantOption,
                    ProductVariantOption.product_variant_id == ProductVariant.id,
                )
                .join(
                    ProductPrice,
                    ProductPrice.product_variant_id == ProductVariantOption.id,
                )
                .filter(
                    ProductVariant.product_id == product.id,
                    ProductPrice.locality_id == locality_uuid,
                    ProductPrice.price_kind == PRICE_KIND_CARD,
                )
                .first()
            )
            if price_row is None or (
                price_row.min_price is None and price_row.max_price is None
            ):
                price_row = (
                    db.session.query(
                        func.min(ProductPrice.price).label('min_price'),
                        func.max(ProductPrice.price).label('max_price'),
                    )
                    .select_from(ProductVariant)
                    .join(
                        ProductVariantOption,
                        ProductVariantOption.product_variant_id == ProductVariant.id,
                    )
                    .join(
                        ProductPrice,
                        ProductPrice.product_variant_id == ProductVariantOption.id,
                    )
                    .filter(
                        ProductVariant.product_id == product.id,
                        ProductPrice.locality_id == locality_uuid,
                        product_price_transfer_filter(),
                    )
                    .first()
                )
            if price_row is not None and (
                price_row.min_price is not None or price_row.max_price is not None
            ):
                precalc_min_price = (
                    float(price_row.min_price) if price_row.min_price is not None else 0.0
                )
                precalc_max_price = (
                    float(price_row.max_price) if price_row.max_price is not None else 0.0
                )

        precalc_min_card_price = None
        precalc_max_card_price = None
        precalc_min_transfer_price = None
        precalc_max_transfer_price = None
        if target_catalog_id:
            card_row = (
                db.session.query(
                    func.min(ProductPrice.price).label('min_price'),
                    func.max(ProductPrice.price).label('max_price'),
                )
                .select_from(ProductVariant)
                .join(
                    ProductVariantOption,
                    ProductVariantOption.product_variant_id == ProductVariant.id,
                )
                .join(
                    ProductPrice,
                    ProductPrice.product_variant_id == ProductVariantOption.id,
                )
                .filter(
                    ProductVariant.product_id == product.id,
                    ProductPrice.catalog_id == target_catalog_id,
                    ProductPrice.price_kind == PRICE_KIND_CARD,
                )
                .first()
            )
            if card_row is not None and (
                card_row.min_price is not None or card_row.max_price is not None
            ):
                precalc_min_card_price = (
                    float(card_row.min_price) if card_row.min_price is not None else 0.0
                )
                precalc_max_card_price = (
                    float(card_row.max_price) if card_row.max_price is not None else 0.0
                )

            transfer_row = (
                db.session.query(
                    func.min(ProductPrice.price).label('min_price'),
                    func.max(ProductPrice.price).label('max_price'),
                )
                .select_from(ProductVariant)
                .join(
                    ProductVariantOption,
                    ProductVariantOption.product_variant_id == ProductVariant.id,
                )
                .join(
                    ProductPrice,
                    ProductPrice.product_variant_id == ProductVariantOption.id,
                )
                .filter(
                    ProductVariant.product_id == product.id,
                    ProductPrice.catalog_id == target_catalog_id,
                    product_price_transfer_filter(),
                )
                .first()
            )
            if transfer_row is not None and (
                transfer_row.min_price is not None or transfer_row.max_price is not None
            ):
                precalc_min_transfer_price = (
                    float(transfer_row.min_price)
                    if transfer_row.min_price is not None
                    else 0.0
                )
                precalc_max_transfer_price = (
                    float(transfer_row.max_price)
                    if transfer_row.max_price is not None
                    else 0.0
                )
        elif locality_uuid is not None:
            transfer_row_loc = (
                db.session.query(
                    func.min(ProductPrice.price).label('min_price'),
                    func.max(ProductPrice.price).label('max_price'),
                )
                .select_from(ProductVariant)
                .join(
                    ProductVariantOption,
                    ProductVariantOption.product_variant_id == ProductVariant.id,
                )
                .join(
                    ProductPrice,
                    ProductPrice.product_variant_id == ProductVariantOption.id,
                )
                .filter(
                    ProductVariant.product_id == product.id,
                    ProductPrice.locality_id == locality_uuid,
                    product_price_transfer_filter(),
                )
                .first()
            )
            if transfer_row_loc is not None and (
                transfer_row_loc.min_price is not None
                or transfer_row_loc.max_price is not None
            ):
                precalc_min_transfer_price = (
                    float(transfer_row_loc.min_price)
                    if transfer_row_loc.min_price is not None
                    else 0.0
                )
                precalc_max_transfer_price = (
                    float(transfer_row_loc.max_price)
                    if transfer_row_loc.max_price is not None
                    else 0.0
                )

        # Algunos precios se guardan con locality_id y sin catalog_id; el listado ya mezcla catálogo.
        # En detalle, si el agregado por catalog_id no encontró filas, completar desde la localidad.
        if locality_uuid is not None:
            if precalc_min_card_price is None or precalc_min_card_price <= 0:
                card_row_fb = (
                    db.session.query(
                        func.min(ProductPrice.price).label('min_price'),
                        func.max(ProductPrice.price).label('max_price'),
                    )
                    .select_from(ProductVariant)
                    .join(
                        ProductVariantOption,
                        ProductVariantOption.product_variant_id == ProductVariant.id,
                    )
                    .join(
                        ProductPrice,
                        ProductPrice.product_variant_id == ProductVariantOption.id,
                    )
                    .filter(
                        ProductVariant.product_id == product.id,
                        ProductPrice.locality_id == locality_uuid,
                        ProductPrice.price_kind == PRICE_KIND_CARD,
                    )
                    .first()
                )
                if card_row_fb is not None and (
                    card_row_fb.min_price is not None or card_row_fb.max_price is not None
                ):
                    precalc_min_card_price = (
                        float(card_row_fb.min_price)
                        if card_row_fb.min_price is not None
                        else 0.0
                    )
                    precalc_max_card_price = (
                        float(card_row_fb.max_price)
                        if card_row_fb.max_price is not None
                        else precalc_min_card_price
                    )

            if precalc_min_transfer_price is None or precalc_min_transfer_price <= 0:
                transfer_row_fb = (
                    db.session.query(
                        func.min(ProductPrice.price).label('min_price'),
                        func.max(ProductPrice.price).label('max_price'),
                    )
                    .select_from(ProductVariant)
                    .join(
                        ProductVariantOption,
                        ProductVariantOption.product_variant_id == ProductVariant.id,
                    )
                    .join(
                        ProductPrice,
                        ProductPrice.product_variant_id == ProductVariantOption.id,
                    )
                    .filter(
                        ProductVariant.product_id == product.id,
                        ProductPrice.locality_id == locality_uuid,
                        product_price_transfer_filter(),
                    )
                    .first()
                )
                if transfer_row_fb is not None and (
                    transfer_row_fb.min_price is not None
                    or transfer_row_fb.max_price is not None
                ):
                    precalc_min_transfer_price = (
                        float(transfer_row_fb.min_price)
                        if transfer_row_fb.min_price is not None
                        else 0.0
                    )
                    precalc_max_transfer_price = (
                        float(transfer_row_fb.max_price)
                        if transfer_row_fb.max_price is not None
                        else precalc_min_transfer_price
                    )

        promo_map = (
            _build_promo_map_for_product_ids(
                [product.id], {product.id: product.category_id}
            )
            if include_promos
            else {}
        )

        product_dict = product.to_dict(
            include_variants=include_variants,
            include_images=include_images,
            locality_id=locality_id,
            include_promos=False,
            locality_to_catalog_map=locality_to_catalog,
            precalculated_min_price=precalc_min_price,
            precalculated_max_price=precalc_max_price,
            include_inventory=False,
            include_all_variant_prices=include_all_variant_prices,
        )
        if include_all_variant_prices and product_dict.get("variants"):
            price_rows = 0
            for v in product_dict["variants"]:
                for o in v.get("options") or []:
                    price_rows += len(o.get("prices") or [])
            logger.info(
                "[get_product] include_all_variant_prices product_id=%s options=%s price_rows_in_json=%s",
                product_id,
                sum(len(v.get("options") or []) for v in product_dict["variants"]),
                price_rows,
            )
        if include_promos:
            product_dict['promos'] = promo_map.get(product.id, [])

        has_crm_stock = check_crm_stock(product.crm_product_id)
        product_dict['has_crm_stock'] = has_crm_stock
        mp = product_dict.get('min_price') or 0
        xp = product_dict.get('max_price') or 0
        if precalc_min_card_price is not None and precalc_min_card_price > 0:
            product_dict['min_card_price'] = precalc_min_card_price
            product_dict['max_card_price'] = precalc_max_card_price if precalc_max_card_price else precalc_min_card_price
        else:
            product_dict['min_card_price'] = mp
            product_dict['max_card_price'] = xp

        if precalc_min_transfer_price is not None and precalc_min_transfer_price > 0:
            product_dict['min_transfer_price'] = precalc_min_transfer_price
            product_dict['max_transfer_price'] = (
                precalc_max_transfer_price
                if precalc_max_transfer_price
                else precalc_min_transfer_price
            )
        
        return jsonify({
            'success': True,
            'data': product_dict
        }), 200
    except Exception as e:
        import traceback
        from flask import current_app
        error_trace = traceback.format_exc()
        # Hacer rollback para limpiar cualquier transacción abortada
        try:
            db.session.rollback()
        except:
            pass
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': error_trace if current_app.config.get('DEBUG') else None
        }), 500

@products_bp.route('/<uuid:product_id>/combos', methods=['GET'])
def get_product_combos(product_id):
    """
    Obtener combos que contienen este producto
    Busca en crm_product_combo_items donde crm_item_product_id = crm_product_id del producto
    """
    try:
        product = Product.query.get_or_404(product_id)

        if not _storefront_may_view_product_detail(product):
            return jsonify({
                'success': False,
                'error': 'Producto no disponible'
            }), 404
        
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
        if not rows:
            return jsonify({
                'success': True,
                'data': []
            }), 200

        combo_crm_ids = list({row.crm_product_id for row in rows})
        items_stmt = text("""
            SELECT
                cpci.crm_combo_product_id,
                cpci.crm_item_product_id,
                cpci.quantity,
                cpci.item_description,
                cp2.description as item_name
            FROM crm_product_combo_items cpci
            JOIN crm_products cp2 ON cp2.crm_product_id = cpci.crm_item_product_id
            WHERE cpci.crm_combo_product_id IN :combo_ids
        """).bindparams(bindparam("combo_ids", expanding=True))
        items_rows = db.session.execute(items_stmt, {"combo_ids": combo_crm_ids}).fetchall()
        items_by_combo = {}
        for item_row in items_rows:
            cid = item_row.crm_combo_product_id
            items_by_combo.setdefault(cid, []).append({
                'crm_product_id': item_row.crm_item_product_id,
                'quantity': item_row.quantity,
                'item_description': item_row.item_description,
                'item_name': item_row.item_name
            })

        product_rows = [row.product_id for row in rows if row.product_id]
        combo_products_map = {}
        if product_rows:
            for p in Product.query.options(
                joinedload(Product.images),
            ).filter(Product.id.in_(product_rows)).all():
                combo_products_map[p.id] = p
        
        combos = []
        for row in rows:
            items = items_by_combo.get(row.crm_product_id, [])
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
            if row.product_id and row.product_id in combo_products_map:
                combo_data['product'] = combo_products_map[row.product_id].to_dict(
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

        # Campos técnicos / colchón (opcionales, mismo criterio que complete CRM)
        _optional_product_fields = (
            'technical_description', 'warranty_months', 'warranty_description', 'materials',
            'basic_color',
            'filling_type', 'max_supported_weight_kg', 'has_pillow_top', 'is_bed_in_box',
            'mattress_firmness', 'mattress_height_cm', 'mattress_fabric_type',
            'has_double_pillow', 'has_moisture_breathers', 'has_side_handles',
            'size_label',
            'viacargo_height_cm', 'viacargo_width_cm', 'viacargo_depth_cm', 'viacargo_weight_kg',
        )
        for _f in _optional_product_fields:
            if _f in data:
                setattr(product, _f, data[_f])
        product.basic_color = normalize_basic_product_color(getattr(product, 'basic_color', None))
        if "show_transfer_price_highlight" in data:
            product.show_transfer_price_highlight = bool(data.get("show_transfer_price_highlight"))
        if "display_reference_price" in data:
            v = data.get("display_reference_price")
            product.display_reference_price = float(v) if v is not None and v != "" else None
        
        # Crear variantes con sus precios
        variants_data = data.get('variants', [])
        # Primero, agrupar todas las options por atributo
        variants_dict = {}  # {attr_name: {variant_obj, options: {attr_value: {stock, prices}}}}
        
        for idx, variant_data in enumerate(variants_data):
            attributes = variant_data.get('attributes', {})
            prices_data = variant_data.get('prices', [])
            if isinstance(prices_data, dict):
                prices_data = [
                    {"catalog_id": k, "price": v}
                    for k, v in prices_data.items()
                    if v and k
                ]
            elif not isinstance(prices_data, list):
                prices_data = []
            card_raw = variant_data.get("card_prices", [])
            if isinstance(card_raw, dict):
                for ck, cv in card_raw.items():
                    if ck and cv:
                        prices_data.append(
                            {"catalog_id": ck, "price": cv, "price_kind": PRICE_KIND_CARD}
                        )
            elif isinstance(card_raw, list):
                for cp in card_raw:
                    if isinstance(cp, dict) and cp.get("price") is not None:
                        prices_data.append(
                            {**cp, "price_kind": cp.get("price_kind") or PRICE_KIND_CARD}
                        )
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
        
        # Precios por opción (FK a product_variant_options.id)
        created_variants = []
        for attr_name, variant_info in variants_dict.items():
            variant = variant_info['variant']
            all_prices = []
            for option_data in variant_info['options'].values():
                option = option_data['option']
                prices_added = set()
                for price_data in option_data['prices']:
                    catalog_id = price_data.get('catalog_id')
                    locality_id = price_data.get('locality_id')
                    price_value = price_data.get('price')
                    pk_raw = price_data.get('price_kind') or PRICE_KIND_TRANSFER
                    price_kind = (
                        PRICE_KIND_CARD
                        if str(pk_raw).lower().strip() == 'card'
                        else PRICE_KIND_TRANSFER
                    )
                    price_key_id = catalog_id or locality_id
                    if not price_key_id or price_value is None:
                        continue
                    dedupe_key = (str(price_key_id), float(price_value), price_kind)
                    if dedupe_key in prices_added:
                        continue
                    prices_added.add(dedupe_key)
                    if catalog_id:
                        from models.catalog import Catalog
                        catalog = Catalog.query.get(catalog_id)
                        if not catalog:
                            continue
                        db.session.add(
                            ProductPrice(
                                product_variant_id=option.id,
                                catalog_id=catalog_id,
                                price=price_value,
                                price_kind=price_kind,
                            )
                        )
                    elif locality_id:
                        locality = Locality.query.get(locality_id)
                        if not locality:
                            continue
                        db.session.add(
                            ProductPrice(
                                product_variant_id=option.id,
                                locality_id=locality_id,
                                price=price_value,
                                price_kind=price_kind,
                            )
                        )
                db.session.flush()
                option_prices = ProductPrice.query.filter_by(
                    product_variant_id=option.id
                ).all()
                all_prices.extend([p.to_dict() for p in option_prices])

            created_variants.append({**variant.to_dict(), 'prices': all_prices})
        
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
        return jsonify({
            'success': False,
            'error': 'Error de integridad: ' + str(e)
        }), 400
    except Exception as e:
        db.session.rollback()
        import traceback
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
        if 'show_transfer_price_highlight' in data:
            product.show_transfer_price_highlight = bool(data.get('show_transfer_price_highlight'))
        if 'display_reference_price' in data:
            v = data.get('display_reference_price')
            product.display_reference_price = float(v) if v is not None and v != '' else None
        if 'basic_color' in data:
            product.basic_color = normalize_basic_product_color(data.get('basic_color'))
        
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
        
        # Buscar productos que coincidan con el término (misma lógica que listado)
        sf = product_text_search_filter(search_term)
        products = Product.query.filter(
            Product.is_active == True,
            sf,
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

