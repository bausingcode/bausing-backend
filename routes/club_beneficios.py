from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import func
import os
import time
import uuid

from database import db
from models.club_beneficios_item import ClubBeneficiosItem
from models.product import Product
from routes.admin import admin_required

club_beneficios_bp = Blueprint("club_beneficios", __name__)

MAX_ITEMS = 200


def _club_admin_debug_enabled():
    if os.getenv("CLUB_BENEFICIOS_ADMIN_DEBUG", "").lower() in ("1", "true", "yes"):
        return True
    try:
        return bool(current_app.config.get("DEBUG_MODE"))
    except RuntimeError:
        return False


def _club_admin_debug(msg: str, **extra):
    if not _club_admin_debug_enabled():
        return
    if extra:
        current_app.logger.info("[club-beneficios admin] %s | %s", msg, extra)
    else:
        current_app.logger.info("[club-beneficios admin] %s", msg)


def _load_options():
    from sqlalchemy.orm import joinedload
    from models.product import ProductSubcategory

    return (
        joinedload(ClubBeneficiosItem.product).joinedload(Product.images),
        joinedload(ClubBeneficiosItem.product).joinedload(Product.category),
        joinedload(ClubBeneficiosItem.product).joinedload(Product.category_option),
        joinedload(ClubBeneficiosItem.product)
        .joinedload(Product.subcategory_associations)
        .joinedload(ProductSubcategory.subcategory),
    )


def _price_map_for_product_ids(product_ids):
    """Una sola query de min/max por producto (catálogo Córdoba capital) para el admin."""
    if not product_ids:
        return {}

    from models.product import (
        ProductVariant,
        ProductVariantOption,
        ProductPrice,
        get_cordoba_capital_catalog_id,
    )

    default = {pid: {"min": 0.0, "max": 0.0} for pid in product_ids}
    catalog_id = get_cordoba_capital_catalog_id()
    if not catalog_id:
        return default

    rows = (
        db.session.query(
            ProductVariant.product_id,
            func.min(ProductPrice.price).label("min_price"),
            func.max(ProductPrice.price).label("max_price"),
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
            ProductVariant.product_id.in_(product_ids),
            ProductPrice.catalog_id == catalog_id,
        )
        .group_by(ProductVariant.product_id)
        .all()
    )

    out = dict(default)
    for r in rows:
        out[r.product_id] = {
            "min": float(r.min_price) if r.min_price is not None else 0.0,
            "max": float(r.max_price) if r.max_price is not None else 0.0,
        }
    return out


def _promos_batch_for_products(products):
    """
    Misma regla que Product.to_dict(include_promos) pero en pocas queries.
    Sin batch, cada producto dispara PromoApplicability + un get por applicability (N+1).
    """
    from models.promo import Promo, PromoApplicability

    if not products:
        return {}

    pid_list = list({p.id for p in products})
    cat_ids = list({p.category_id for p in products if p.category_id})

    clauses = [
        PromoApplicability.applies_to == 'all',
        db.and_(
            PromoApplicability.applies_to == 'product',
            PromoApplicability.product_id.in_(pid_list),
        ),
    ]
    if cat_ids:
        clauses.append(
            db.and_(
                PromoApplicability.applies_to == 'category',
                PromoApplicability.category_id.in_(cat_ids),
            )
        )

    apps = PromoApplicability.query.filter(db.or_(*clauses)).all()
    promo_ids = {app.promo_id for app in apps}
    promos_by_id = {
        p.id: p
        for p in (Promo.query.filter(Promo.id.in_(promo_ids)).all() if promo_ids else [])
    }

    apps_all = [a for a in apps if a.applies_to == 'all']
    by_pid = {}
    for a in apps:
        if a.applies_to == 'product' and a.product_id:
            by_pid.setdefault(a.product_id, []).append(a)
    by_cid = {}
    for a in apps:
        if a.applies_to == 'category' and a.category_id:
            by_cid.setdefault(a.category_id, []).append(a)

    out = {}
    for prod in products:
        merged = apps_all + by_pid.get(prod.id, [])
        if prod.category_id:
            merged.extend(by_cid.get(prod.category_id, []))
        plist = []
        seen = set()
        for app in merged:
            promo = promos_by_id.get(app.promo_id)
            if not promo or promo.id in seen:
                continue
            if promo.is_valid():
                seen.add(promo.id)
                plist.append(promo.to_dict())
        out[prod.id] = plist

    return out


def _items_to_payload(items):
    price_ids = []
    products_for_promos = []
    seen_pid = set()
    for it in items:
        if it.product and it.product.id not in seen_pid:
            seen_pid.add(it.product.id)
            price_ids.append(it.product.id)
            products_for_promos.append(it.product)
    price_map = _price_map_for_product_ids(price_ids)
    promos_map = _promos_batch_for_products(products_for_promos)

    def _item(i):
        base = i.to_dict(
            include_product=True,
            product_price_map=price_map,
            product_promos_map=promos_map,
        )
        return {
            'id': str(i.id),
            'section': 'club_beneficios',
            'position': int(i.position),
            'product_id': str(i.product_id),
            'product': base.get('product'),
            'created_at': i.created_at.isoformat() if i.created_at else None,
            'updated_at': i.updated_at.isoformat() if i.updated_at else None,
        }

    return {
        'items': [_item(it) for it in items],
        'total': len(items),
    }


def _parse_product_ids(data):
    raw_ids = data.get('product_ids', [])
    if raw_ids is None:
        return []
    if not isinstance(raw_ids, list):
        raise ValueError('Parámetro "product_ids" inválido')

    out = []
    seen = set()
    for raw in raw_ids:
        if raw is None:
            continue
        s = str(raw).strip()
        if not s:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _save_published_list(product_ids):
    if len(product_ids) > MAX_ITEMS:
        raise ValueError(f"Demasiados productos (máximo {MAX_ITEMS})")

    product_uuids = []
    for pid in product_ids:
        try:
            product_uuids.append(uuid.UUID(str(pid)))
        except (ValueError, TypeError):
            raise ValueError('ID de producto inválido')

    if product_uuids:
        existing = (
            Product.query.filter(Product.id.in_(product_uuids))
            .with_entities(Product.id)
            .all()
        )
        existing_ids = {str(r.id) for r in existing}
        missing = [str(u) for u in product_uuids if str(u) not in existing_ids]
        if missing:
            raise ValueError('Producto no encontrado')

    ClubBeneficiosItem.query.delete(synchronize_session=False)

    for pos, pid in enumerate(product_uuids):
        db.session.add(ClubBeneficiosItem(position=pos, product_id=pid))

    db.session.commit()


@club_beneficios_bp.route('/admin/club-beneficios', methods=['GET'])
@admin_required
def get_admin_club_beneficios():
    t0 = time.perf_counter()
    has_auth = bool(request.headers.get("Authorization"))
    _club_admin_debug(
        "GET /admin/club-beneficios",
        remote_addr=request.remote_addr,
        has_authorization_header=has_auth,
    )
    try:
        items = (
            ClubBeneficiosItem.query.options(*_load_options())
            .order_by(ClubBeneficiosItem.position)
            .all()
        )
        payload = _items_to_payload(items)
        ms = (time.perf_counter() - t0) * 1000
        _club_admin_debug(
            "GET ok",
            item_count=len(items),
            ms_rounded=round(ms, 2),
        )
        return jsonify({'success': True, 'data': payload}), 200
    except Exception as e:
        current_app.logger.error("Error al obtener club beneficios: %s", str(e), exc_info=True)
        return jsonify({'success': False, 'error': 'Error interno del servidor'}), 500


@club_beneficios_bp.route('/admin/club-beneficios', methods=['PUT', 'POST'])
@admin_required
def save_admin_club_beneficios():
    t0 = time.perf_counter()
    _club_admin_debug(
        f"{request.method} /admin/club-beneficios",
        remote_addr=request.remote_addr,
    )
    try:
        data = request.get_json() or {}
        product_ids = _parse_product_ids(data)
        _club_admin_debug("save parsed", product_id_count=len(product_ids))
        _save_published_list(product_ids)

        items = (
            ClubBeneficiosItem.query.options(*_load_options())
            .order_by(ClubBeneficiosItem.position)
            .all()
        )
        ms = (time.perf_counter() - t0) * 1000
        _club_admin_debug(
            "save ok",
            item_count=len(items),
            ms_rounded=round(ms, 2),
        )
        return jsonify({'success': True, 'data': _items_to_payload(items)}), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error al guardar club beneficios: %s", str(e), exc_info=True)
        return jsonify({'success': False, 'error': 'Error interno del servidor'}), 500


@club_beneficios_bp.route('/admin/club-beneficios/publish', methods=['POST'])
@admin_required
def publish_admin_club_beneficios():
    return save_admin_club_beneficios()


@club_beneficios_bp.route('/admin/club-beneficios/draft', methods=['DELETE'])
@admin_required
def discard_admin_club_beneficios_draft():
    return jsonify({'success': True, 'message': 'OK'}), 200


def _club_batch_main_image_urls(product_ids):
    """Primera imagen por producto (por posición asc) en una sola query."""
    if not product_ids:
        return {}
    from models.image import ProductImage
    from sqlalchemy import func

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
        db.session.query(ProductImage.product_id, ProductImage.image_url, rn)
        .filter(ProductImage.product_id.in_(product_ids))
    ).subquery()
    rows = (
        db.session.query(subq.c.product_id, subq.c.image_url)
        .filter(subq.c.rn == 1)
        .all()
    )
    return {str(pid): str(url).strip() for pid, url in rows if url and str(url).strip()}


@club_beneficios_bp.route('/club-beneficios/quick', methods=['GET'])
def get_public_club_beneficios_quick():
    try:
        from sqlalchemy.orm import joinedload

        items = (
            ClubBeneficiosItem.query.options(
                joinedload(ClubBeneficiosItem.product).joinedload(Product.category),
                joinedload(ClubBeneficiosItem.product).joinedload(Product.category_option),
            )
            .order_by(ClubBeneficiosItem.position)
            .all()
        )

        active_items = [it for it in items if it.product and it.product.is_active]
        product_ids = [it.product.id for it in active_items]
        main_image_by_pid = _club_batch_main_image_urls(product_ids)

        products = []
        for it in active_items:
            p = it.product.to_dict(
                include_variants=False,
                include_images=False,
                include_promos=False,
                include_inventory=False,
                precalculated_min_price=0.0,
                precalculated_max_price=0.0,
                precalculated_main_image=main_image_by_pid.get(str(it.product.id)),
            )
            p['min_price'] = None
            p['max_price'] = None
            p['price_range'] = None
            p['promos'] = []
            products.append(p)

        resp = jsonify({'success': True, 'data': products})
        resp.headers['Cache-Control'] = 'public, max-age=20'
        return resp, 200
    except Exception as e:
        current_app.logger.error("Error en club beneficios quick: %s", str(e), exc_info=True)
        return jsonify({'success': False, 'error': 'Error interno del servidor'}), 500
