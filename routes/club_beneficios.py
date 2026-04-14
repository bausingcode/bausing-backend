from flask import Blueprint, request, jsonify
from sqlalchemy import func
import uuid

from database import db
from models.club_beneficios_item import ClubBeneficiosItem
from models.product import Product
from routes.admin import admin_required

club_beneficios_bp = Blueprint("club_beneficios", __name__)

MAX_ITEMS = 200


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


def _items_to_payload(items):
    price_ids = []
    seen_pid = set()
    for it in items:
        if it.product and it.product.id not in seen_pid:
            seen_pid.add(it.product.id)
            price_ids.append(it.product.id)
    price_map = _price_map_for_product_ids(price_ids)

    def _item(i):
        base = i.to_dict(include_product=True, product_price_map=price_map)
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
    try:
        items = (
            ClubBeneficiosItem.query.options(*_load_options())
            .order_by(ClubBeneficiosItem.position)
            .all()
        )
        return jsonify({'success': True, 'data': _items_to_payload(items)}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@club_beneficios_bp.route('/admin/club-beneficios', methods=['PUT', 'POST'])
@admin_required
def save_admin_club_beneficios():
    try:
        data = request.get_json() or {}
        product_ids = _parse_product_ids(data)
        _save_published_list(product_ids)

        items = (
            ClubBeneficiosItem.query.options(*_load_options())
            .order_by(ClubBeneficiosItem.position)
            .all()
        )
        return jsonify({'success': True, 'data': _items_to_payload(items)}), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@club_beneficios_bp.route('/admin/club-beneficios/publish', methods=['POST'])
@admin_required
def publish_admin_club_beneficios():
    return save_admin_club_beneficios()


@club_beneficios_bp.route('/admin/club-beneficios/draft', methods=['DELETE'])
@admin_required
def discard_admin_club_beneficios_draft():
    return jsonify({'success': True, 'message': 'OK'}), 200


@club_beneficios_bp.route('/club-beneficios/quick', methods=['GET'])
def get_public_club_beneficios_quick():
    try:
        from sqlalchemy.orm import joinedload

        items = (
            ClubBeneficiosItem.query.options(
                joinedload(ClubBeneficiosItem.product).joinedload(Product.images),
                joinedload(ClubBeneficiosItem.product).joinedload(Product.category),
                joinedload(ClubBeneficiosItem.product).joinedload(Product.category_option),
            )
            .order_by(ClubBeneficiosItem.position)
            .all()
        )

        products = []
        for it in items:
            if not it.product:
                continue
            if not it.product.is_active:
                continue
            p = it.product.to_dict(
                include_variants=False,
                include_images=False,
                include_promos=False,
                include_inventory=False,
                precalculated_min_price=0.0,
                precalculated_max_price=0.0,
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
        return jsonify({'success': False, 'error': str(e)}), 500
