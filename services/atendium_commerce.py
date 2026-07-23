# -*- coding: utf-8 -*-
"""
Helpers de comercio para la API Atendium (zona, precios, envío, handoff, cupones).
"""
from __future__ import annotations

import secrets
import uuid
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from database import db
from models.catalog import Catalog, LocalityCatalog
from models.coupon import Coupon
from models.coupon_category_discount import CouponCategoryDiscount
from models.locality import Locality
from models.product import Product
from models.settings import SystemSettings
from models.user import User
from models.wallet import Wallet
from routes.auth import geocode_address_with_fallback
from routes.homepage_distribution import _build_homepage_prices_map
from routes.locality_detection import find_locality_by_coordinates
from routes.orders import format_estimated_delivery, get_crm_zone_id_from_locality
from routes.referrals import validate_referral_code_logic
from routes.settings import (
    ACCESSORIES_CATALOG_CATEGORY_ID,
    PAIS_CATALOG_ID,
    _resolve_root_category_uuid,
)
from utils.coupon_order import (
    compute_coupon_discount_amount,
    get_club_beneficios_product_id_set,
    normalize_coupon_code,
    validate_coupon_row,
)

HANDOFF_MESSAGES = {
    "pais_catalog": "Esta zona usa Catálogo País: la venta debe completarla un asesor.",
    "third_party_card": "En zona de transporte tercerizado con tarjeta, un asesor debe completar la venta.",
    "third_party_transfer": "En zona de transporte tercerizado con transferencia, un asesor debe completar la venta.",
}


def estimated_delivery_payload(catalog: Optional[Catalog]) -> Optional[Dict[str, Any]]:
    if not catalog:
        return None
    days_min = catalog.estimated_delivery_days_min
    days_max = catalog.estimated_delivery_days_max
    if days_min is None and days_max is None:
        return None
    label = format_estimated_delivery(catalog)
    return {
        "min_days": days_min,
        "max_days": days_max,
        "label": label,
    }


def get_whatsapp_phone() -> Optional[str]:
    setting = SystemSettings.query.filter_by(key="general.phone").first()
    return setting.value if setting and setting.value else None


def normalize_phone_digits(phone: Optional[str]) -> str:
    if not phone:
        return ""
    return "".join(c for c in str(phone) if c.isdigit())


def phones_match(a: Optional[str], b: Optional[str]) -> bool:
    da, db_ = normalize_phone_digits(a), normalize_phone_digits(b)
    if not da or not db_:
        return False
    if da == db_:
        return True
    # Comparar últimos 8–10 dígitos (local vs +54…)
    for n in (10, 8):
        if len(da) >= n and len(db_) >= n and da[-n:] == db_[-n:]:
            return True
    return False


def catalog_for_locality(locality_id) -> Tuple[Optional[Catalog], Optional[str]]:
    try:
        lid = uuid.UUID(str(locality_id))
    except (ValueError, TypeError):
        return None, None
    row = LocalityCatalog.query.filter_by(locality_id=lid).first()
    if not row:
        return None, None
    return row.catalog, str(row.catalog_id)


def build_zone_from_coords(lon: float, lat: float) -> Dict[str, Any]:
    from models.crm_delivery_zone import CrmDeliveryZone, CrmZoneLocality

    locality, shipping_zone_locality = find_locality_by_coordinates(lon, lat)
    if not locality:
        raise ValueError("No se encontró una localidad para las coordenadas proporcionadas")

    is_third_party = False
    shipping_price = None
    if shipping_zone_locality:
        is_third_party = bool(shipping_zone_locality.is_third_party_transport)
        if shipping_zone_locality.shipping_price is not None:
            shipping_price = float(shipping_zone_locality.shipping_price)

    crm_zone_id = None
    zone_locality = CrmZoneLocality.query.filter_by(locality_id=locality.id).first()
    if zone_locality:
        crm_zone_id = zone_locality.crm_zone_id
        if not shipping_zone_locality:
            is_third_party = bool(zone_locality.is_third_party_transport)
            if zone_locality.shipping_price is not None:
                shipping_price = float(zone_locality.shipping_price)
    else:
        try:
            crm_zone = CrmDeliveryZone.query.filter(
                CrmDeliveryZone.name.ilike(f"%{locality.name}%"),
                CrmDeliveryZone.crm_deleted_at.is_(None),
            ).first()
            if crm_zone:
                crm_zone_id = crm_zone.crm_zone_id
        except Exception:
            pass

    if crm_zone_id is None:
        crm_zone_id = get_crm_zone_id_from_locality(locality.name)

    catalog, catalog_id = catalog_for_locality(locality.id)
    is_pais = str(catalog_id) == PAIS_CATALOG_ID if catalog_id else False

    return {
        "locality": {
            "id": str(locality.id),
            "name": locality.name,
        },
        "coordinates": {"lon": lon, "lat": lat},
        "crm_zone_id": crm_zone_id,
        "catalog_id": catalog_id,
        "is_pais_catalog": is_pais,
        "is_third_party_transport": is_third_party,
        "shipping_price": shipping_price,
        "estimated_delivery": estimated_delivery_payload(catalog),
    }


def resolve_zone_from_address(address: Dict[str, Any]) -> Dict[str, Any]:
    lat = address.get("lat")
    lon = address.get("lon")
    if lat is not None and lon is not None:
        try:
            return build_zone_from_coords(float(lon), float(lat))
        except (TypeError, ValueError):
            pass

    street = (address.get("street") or "").strip()
    number = str(address.get("number") or "").strip()
    city = (address.get("city") or address.get("locality") or "").strip()
    postal_code = str(address.get("postal_code") or "").strip()
    province_name = (address.get("province") or address.get("province_name") or "").strip() or None

    if not street or not city:
        raise ValueError("Se requiere street y city (o lat/lon) para resolver la zona")

    geocoded = geocode_address_with_fallback(
        street, number, city, postal_code, province_name=province_name
    )
    if not geocoded:
        raise ValueError("No se pudo geocodificar la dirección")

    lat_str, lon_str = geocoded.split(",")
    return build_zone_from_coords(float(lon_str.strip()), float(lat_str.strip()))


def unit_price_for_payment(price_info: Dict[str, Any], payment_method: str) -> float:
    method = (payment_method or "transfer").lower()
    if method == "card":
        base = (
            price_info.get("min_card_price")
            or price_info.get("min_price")
            or 0
        )
    else:
        base = (
            price_info.get("min_transfer_price")
            or price_info.get("min_price")
            or 0
        )
    try:
        base = float(base or 0)
    except (TypeError, ValueError):
        base = 0.0

    promos = price_info.get("promos") or []
    if promos and base > 0:
        promo = promos[0] if isinstance(promos[0], dict) else None
        if promo:
            dtype = str(promo.get("discount_type") or promo.get("type") or "").lower()
            try:
                dval = float(promo.get("discount_value") or promo.get("value") or 0)
            except (TypeError, ValueError):
                dval = 0.0
            if dtype in ("percentage", "percent") and dval > 0:
                base = max(0.0, base * (1 - dval / 100.0))
            elif dtype in ("fixed", "amount") and dval > 0:
                base = max(0.0, base - dval)
    return round(base, 2)


def price_lines_for_items(
    items: List[Dict[str, Any]],
    locality_id: Optional[str],
    payment_method: str,
) -> Tuple[List[Dict[str, Any]], float]:
    product_ids = [str(it.get("product_id")) for it in items if it.get("product_id")]
    prices_map = _build_homepage_prices_map(product_ids, locality_id)
    lines = []
    subtotal = 0.0
    for it in items:
        pid = str(it.get("product_id") or "")
        try:
            qty = int(it.get("quantity") or 1)
        except (TypeError, ValueError):
            qty = 1
        if qty < 1 or not pid:
            continue
        info = prices_map.get(pid) or {}
        unit = unit_price_for_payment(info, payment_method)
        if unit <= 0:
            raise ValueError(f"Sin precio disponible para el producto {pid} en esta localidad")
        line_total = round(unit * qty, 2)
        subtotal += line_total
        product = Product.query.get(uuid.UUID(pid))
        lines.append(
            {
                "product_id": pid,
                "product_name": product.name if product else None,
                "quantity": qty,
                "unit_price": unit,
                "line_total": line_total,
            }
        )
    return lines, round(subtotal, 2)


def cart_is_accessories_only(product_ids: List[str]) -> bool:
    if not product_ids:
        return False
    try:
        target = uuid.UUID(ACCESSORIES_CATALOG_CATEGORY_ID)
        uuids = [uuid.UUID(str(pid)) for pid in product_ids]
    except (ValueError, TypeError):
        return False
    products = Product.query.filter(Product.id.in_(uuids)).all()
    if len(products) != len(set(uuids)):
        return False
    return all(
        p.category_id and _resolve_root_category_uuid(p.category_id) == target
        for p in products
    )


def quote_accessories_shipping(catalog_id: Optional[str], product_ids: List[str]) -> Optional[float]:
    if not catalog_id or str(catalog_id) == PAIS_CATALOG_ID:
        return None
    if not cart_is_accessories_only(product_ids):
        return None
    try:
        catalog = Catalog.query.get(uuid.UUID(str(catalog_id)))
    except (ValueError, TypeError):
        return None
    if not catalog or catalog.accessories_shipping_price is None:
        return None
    price = float(catalog.accessories_shipping_price)
    return price if price > 0 else None


def quote_viacargo_shipping(items: List[Dict[str, Any]], postal_code: str, declared: float) -> float:
    from routes.viacargo_shipping import public_viacargo_cotizar

    payload = {
        "items": [{"product_id": it["product_id"], "quantity": it["quantity"]} for it in items],
        "codigo_postal_destinatario": postal_code,
        "importe_valor_declarado": int(round(float(declared or 0))),
    }
    with current_app.test_request_context(
        "/public/viacargo-cotizar", method="POST", json=payload
    ):
        resp = public_viacargo_cotizar()
    body, status = resp if isinstance(resp, tuple) else (resp, 200)
    data = body.get_json(silent=True) if hasattr(body, "get_json") else None
    if status != 200 or not data or not data.get("success"):
        err = (data or {}).get("error") or "No se pudo cotizar el envío Vía Cargo"
        raise ValueError(err)
    total = (data.get("data") or {}).get("total")
    if total is None:
        total = data.get("total")
    return float(total or 0)


def resolve_shipping(
    zone: Dict[str, Any],
    items: List[Dict[str, Any]],
    postal_code: Optional[str],
    subtotal: float,
) -> Tuple[float, str]:
    """Devuelve (shipping_cost, shipping_kind)."""
    product_ids = [it["product_id"] for it in items]
    if zone.get("is_third_party_transport") and zone.get("shipping_price") is not None:
        return float(zone["shipping_price"]), "third_party"
    if zone.get("is_pais_catalog"):
        if not postal_code:
            raise ValueError("Código postal requerido para cotizar envío Catálogo País")
        cost = quote_viacargo_shipping(items, str(postal_code), subtotal)
        return cost, "viacargo"
    acc = quote_accessories_shipping(zone.get("catalog_id"), product_ids)
    if acc is not None:
        return float(acc), "accessories"
    return 0.0, "none"


def evaluate_handoff(zone: Dict[str, Any], payment_method: str) -> Optional[Dict[str, Any]]:
    method = (payment_method or "").lower()
    reason = None
    if zone.get("is_pais_catalog"):
        reason = "pais_catalog"
    elif zone.get("is_third_party_transport") and method == "card":
        reason = "third_party_card"
    elif zone.get("is_third_party_transport") and method == "transfer":
        reason = "third_party_transfer"

    if not reason:
        return None

    return {
        "can_create_order": False,
        "requires_human_handoff": True,
        "handoff_reason": reason,
        "handoff_message": HANDOFF_MESSAGES.get(
            reason, "Esta venta debe completarla un asesor."
        ),
        "whatsapp_phone": get_whatsapp_phone(),
    }


def preview_coupon(
    coupon_code: Optional[str],
    priced_lines: List[Dict[str, Any]],
) -> Tuple[float, Optional[Dict[str, Any]]]:
    code = normalize_coupon_code(coupon_code)
    if not code:
        return 0.0, None

    c = Coupon.query.filter(func.lower(Coupon.code) == code.lower()).first()
    if not c:
        raise ValueError("Cupón no encontrado")
    vmsg = validate_coupon_row(c)
    if vmsg:
        raise ValueError(vmsg)

    disc_lines = []
    for line in priced_lines:
        disc_lines.append(
            {
                "product_id": line["product_id"],
                "precio_total_original": line["line_total"],
            }
        )
        try:
            prod = Product.query.get(uuid.UUID(line["product_id"]))
            if prod:
                disc_lines[-1]["category_id"] = str(prod.category_id) if prod.category_id else None
                disc_lines[-1]["subcategory_ids"] = [
                    str(a.subcategory_id) for a in (prod.subcategory_associations or [])
                ]
        except Exception:
            pass

    cat_rules = CouponCategoryDiscount.query.filter_by(coupon_id=c.id).all()
    cat_rules_list = [r.to_dict() for r in cat_rules]
    club_ids = get_club_beneficios_product_id_set()
    total_disc, _discounts, cerr = compute_coupon_discount_amount(
        c, disc_lines, club_ids, cat_rules_list or None
    )
    if cerr:
        raise ValueError(cerr)

    return round(float(total_disc), 2), {
        "code": c.code,
        "discount_amount": round(float(total_disc), 2),
        "discount_type": c.discount_type,
        "discount_value": float(c.discount_value) if c.discount_value is not None else 0.0,
        "club_beneficios_only": bool(c.club_beneficios_only),
    }


def validate_referral(referral_code: Optional[str], user_id=None) -> Optional[str]:
    code = (referral_code or "").strip().upper()
    if not code:
        return None
    result = validate_referral_code_logic(code, user_id=user_id)
    if not result.get("valid"):
        raise ValueError(result.get("message") or "Código de referido inválido")
    return code


def find_or_create_user(customer: Dict[str, Any]) -> User:
    email = (customer.get("email") or "").strip().lower()
    first_name = (customer.get("first_name") or "").strip()
    last_name = (customer.get("last_name") or "").strip()
    phone = customer.get("phone")
    dni = customer.get("dni") or customer.get("document_number")

    if not email or "@" not in email:
        raise ValueError("Email del cliente requerido")
    if not first_name or not last_name:
        raise ValueError("Nombre y apellido del cliente son requeridos")

    user = User.query.filter_by(email=email).first()
    if user:
        changed = False
        if phone and not user.phone:
            user.phone = phone
            changed = True
        if dni and not user.dni:
            user.dni = str(dni)
            changed = True
        if changed:
            db.session.commit()
        return user

    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    password = "".join(secrets.choice(alphabet) for _ in range(12))
    user = User(
        email=email,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        dni=str(dni) if dni else None,
        email_verified=True,
        referral_code=User.generate_referral_code(),
    )
    user.set_password(password)
    try:
        db.session.add(user)
        db.session.flush()
        db.session.add(Wallet(user_id=user.id, balance=0.00, is_blocked=False))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = User.query.filter_by(email=email).first()
        if existing:
            return existing
        raise
    return user


def search_products(
    q: Optional[str],
    locality_id: Optional[str],
    category_id: Optional[str],
    page: int = 1,
    per_page: int = 20,
) -> Dict[str, Any]:
    from routes.products import product_text_search_filter

    page = max(1, int(page or 1))
    per_page = min(max(1, int(per_page or 20)), 50)

    query = Product.query.filter(Product.is_active.is_(True), Product.crm_product_id.isnot(None))
    if q and q.strip():
        filt = product_text_search_filter(q.strip())
        if filt is not None:
            query = query.filter(filt)
    if category_id:
        try:
            query = query.filter(Product.category_id == uuid.UUID(str(category_id)))
        except (ValueError, TypeError):
            pass

    pagination = query.order_by(Product.name.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    products = pagination.items
    ids = [str(p.id) for p in products]
    prices_map = _build_homepage_prices_map(ids, locality_id) if ids else {}
    catalog, _cid = catalog_for_locality(locality_id) if locality_id else (None, None)
    delivery = estimated_delivery_payload(catalog)

    items = []
    for p in products:
        info = prices_map.get(str(p.id)) or {}
        items.append(
            {
                "id": str(p.id),
                "name": p.name,
                "description": (p.description or "")[:280] if p.description else None,
                "category_id": str(p.category_id) if p.category_id else None,
                "main_image": p.get_main_image(),
                "price_transfer": info.get("min_transfer_price") or info.get("min_price"),
                "price_card": info.get("min_card_price") or info.get("min_price"),
                "promos": info.get("promos") or [],
            }
        )

    return {
        "products": items,
        "estimated_delivery": delivery,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total,
            "pages": pagination.pages,
        },
    }


def product_detail(product_id: str, locality_id: Optional[str]) -> Dict[str, Any]:
    try:
        pid = uuid.UUID(str(product_id))
    except (ValueError, TypeError):
        raise ValueError("product_id inválido")
    product = Product.query.filter_by(id=pid, is_active=True).first()
    if not product:
        raise ValueError("Producto no encontrado")
    prices_map = _build_homepage_prices_map([str(pid)], locality_id)
    info = prices_map.get(str(pid)) or {}
    catalog, _cid = catalog_for_locality(locality_id) if locality_id else (None, None)
    return {
        "id": str(product.id),
        "name": product.name,
        "description": product.description,
        "category_id": str(product.category_id) if product.category_id else None,
        "main_image": product.get_main_image(),
        "price_transfer": info.get("min_transfer_price") or info.get("min_price"),
        "price_card": info.get("min_card_price") or info.get("min_price"),
        "promos": info.get("promos") or [],
        "estimated_delivery": estimated_delivery_payload(catalog),
        "prices_raw": info,
    }


def build_full_quote(
    address: Dict[str, Any],
    items: List[Dict[str, Any]],
    payment_method: str,
    coupon_code: Optional[str] = None,
    referral_code: Optional[str] = None,
    user_id=None,
) -> Dict[str, Any]:
    if not items:
        raise ValueError("items es requerido")
    method = (payment_method or "transfer").lower()
    if method not in ("cash", "transfer", "card"):
        raise ValueError("payment_method debe ser cash, transfer o card")

    zone = resolve_zone_from_address(address)
    priced_lines, subtotal = price_lines_for_items(
        items, zone["locality"]["id"], method
    )
    if not priced_lines:
        raise ValueError("No hay ítems válidos para cotizar")

    coupon_discount, coupon_info = preview_coupon(coupon_code, priced_lines)
    referral = validate_referral(referral_code, user_id=user_id)

    shipping_cost, shipping_kind = resolve_shipping(
        zone,
        priced_lines,
        address.get("postal_code"),
        subtotal,
    )
    subtotal_after = max(0.0, round(subtotal - coupon_discount, 2))
    total = round(subtotal_after + shipping_cost, 2)

    handoff = evaluate_handoff(zone, method)
    can_create = handoff is None

    result = {
        "zone": zone,
        "payment_method": method,
        "items": priced_lines,
        "subtotal": subtotal,
        "coupon": coupon_info,
        "coupon_discount": coupon_discount,
        "subtotal_after_coupon": subtotal_after,
        "referral_code": referral,
        "shipping_cost": shipping_cost,
        "shipping_kind": shipping_kind,
        "total": total,
        "estimated_delivery": zone.get("estimated_delivery"),
        "can_create_order": can_create,
        "requires_human_handoff": not can_create,
    }
    if handoff:
        result.update(handoff)
        result["quote_summary"] = {
            "items": priced_lines,
            "subtotal": subtotal,
            "coupon_discount": coupon_discount,
            "shipping_cost": shipping_cost,
            "total": total,
        }
    return result
