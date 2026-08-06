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
from models.product import Product, ProductSubcategory
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


def _normalize_locality_id(locality_id: Optional[str]) -> Optional[str]:
    if locality_id in (None, ""):
        return None
    loc = str(locality_id).strip()
    if loc in ("null", "undefined", "None"):
        return None
    return loc


def _positive_price(*candidates) -> Optional[float]:
    for raw in candidates:
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _format_ars(value: float) -> str:
    return f"${value:,.0f}".replace(",", ".")


def _shipping_summary_payload(
    *,
    is_third_party: bool,
    shipping_price: Optional[float],
    is_pais: bool,
) -> Dict[str, Any]:
    """Solo 2 envíos pagos: tercerizado y Vía Cargo. El resto es gratuito."""
    if is_third_party and shipping_price is not None:
        return {
            "kind": "third_party",
            "is_free": False,
            "cost": float(shipping_price),
            "cost_label": _format_ars(float(shipping_price)),
            "message": f"Envío tercerizado: {_format_ars(float(shipping_price))}",
        }
    if is_pais:
        return {
            "kind": "viacargo",
            "is_free": False,
            "cost": None,
            "cost_label": None,
            "message": (
                "Envío Vía Cargo: para el monto exacto hace falta cotizar "
                "con los productos y el código postal"
            ),
        }
    return {
        "kind": "free",
        "is_free": True,
        "cost": 0.0,
        "cost_label": "$0",
        "message": "Envío gratuito",
    }


def _build_pais_catalog_zone(lon: float, lat: float) -> Dict[str, Any]:
    """
    Fallback cuando el punto no cae en ningún polígono de zona:
    misma lógica que /detect-locality → Catálogo País.
    """
    import uuid as uuid_lib

    try:
        pais_uuid = uuid_lib.UUID(PAIS_CATALOG_ID)
    except (ValueError, TypeError):
        raise ValueError("Catálogo País no configurado")

    catalog = Catalog.query.get(pais_uuid)
    if not catalog:
        raise ValueError("Catálogo País no encontrado")

    locality_assoc = LocalityCatalog.query.filter_by(catalog_id=catalog.id).first()
    locality = locality_assoc.locality if locality_assoc else None
    delivery = estimated_delivery_payload(catalog)

    return {
        "locality": {
            "id": str(locality.id) if locality else None,
            "name": locality.name if locality else "Catálogo País",
        },
        "coordinates": {"lon": lon, "lat": lat},
        "crm_zone_id": None,
        "catalog_id": str(catalog.id),
        "catalog_name": catalog.name,
        "is_pais_catalog": True,
        "is_third_party_transport": False,
        "shipping_price": None,
        "estimated_delivery": delivery,
        "shipping_summary": _shipping_summary_payload(
            is_third_party=False, shipping_price=None, is_pais=True
        ),
        "fallback": "pais_catalog",
        "fallback_reason": (
            "No se encontró zona de entrega para las coordenadas; "
            "se usa Catálogo País (Vía Cargo)"
        ),
    }


def build_zone_from_coords(lon: float, lat: float) -> Dict[str, Any]:
    from models.crm_delivery_zone import CrmDeliveryZone, CrmZoneLocality

    locality, shipping_zone_locality = find_locality_by_coordinates(lon, lat)
    if not locality:
        # Paridad con la web (/detect-locality): fuera de polígono → Catálogo País
        return _build_pais_catalog_zone(lon, lat)

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
    # Si la localidad no tiene catálogo mapeado, también País
    if not catalog_id:
        return _build_pais_catalog_zone(lon, lat)

    is_pais = str(catalog_id) == PAIS_CATALOG_ID
    delivery = estimated_delivery_payload(catalog)
    shipping_summary = _shipping_summary_payload(
        is_third_party=is_third_party,
        shipping_price=shipping_price,
        is_pais=is_pais,
    )

    return {
        "locality": {
            "id": str(locality.id),
            "name": locality.name,
        },
        "coordinates": {"lon": lon, "lat": lat},
        "crm_zone_id": crm_zone_id,
        "catalog_id": catalog_id,
        "catalog_name": catalog.name if catalog else None,
        "is_pais_catalog": is_pais,
        "is_third_party_transport": is_third_party,
        "shipping_price": shipping_price if is_third_party else None,
        "estimated_delivery": delivery,
        "shipping_summary": shipping_summary,
    }


def _normalize_city_province(city: str, province_name: Optional[str]) -> Tuple[str, Optional[str]]:
    """Normaliza typos frecuentes del bot (corodba, cba capital, etc.)."""
    import re
    import unicodedata

    def _norm(value: str) -> str:
        text = unicodedata.normalize("NFKD", value or "")
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return re.sub(r"\s+", " ", text).strip().lower()

    city_clean = (city or "").strip()
    prov_clean = (province_name or "").strip() or None
    city_n = _norm(city_clean)

    # Typos / variantes Córdoba Capital
    cordoba_aliases = {
        "cordoba",
        "cba",
        "cordoba capital",
        "cba capital",
        "capital cordoba",
        "capital de cordoba",
        "corodba",
        "corodba capital",
        "cordova",
        "cordova capital",
    }
    if city_n in cordoba_aliases or city_n.replace(" ", "") in {
        "cordobacapital",
        "corodbacapital",
        "cbacapital",
    }:
        city_clean = "Córdoba"
        if not prov_clean:
            prov_clean = "Córdoba"
    elif "cordoba" in city_n or "corodba" in city_n or "cordova" in city_n:
        # "Villa Carlos Paz, Cordoba" ya viene separado; si city trae typo suelto
        if city_n.startswith("corodba") or city_n.startswith("cordova"):
            city_clean = city_clean.replace("corodba", "córdoba").replace("Corodba", "Córdoba")
            city_clean = city_clean.replace("cordova", "córdoba").replace("Cordova", "Córdoba")
        if not prov_clean and "capital" in city_n:
            city_clean = "Córdoba"
            prov_clean = "Córdoba"

    return city_clean, prov_clean


def parse_freeform_address(text: str) -> Dict[str, str]:
    """
    Parsea frases típicas de WhatsApp:
    "rodolfo martinez 6034, cordoba capital, 5021"
    "Rodolfo Martínez 6034 Córdoba Capital CP 5021"
    """
    import re

    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw:
        return {}

    postal_code = ""
    # Preferir CP explícito o el de 4 dígitos al FINAL (no la altura de la calle)
    cp_explicit = re.search(
        r"(?:cp|codigo postal|código postal)\s*([A-Z]?\d{4})\b", raw, re.I
    )
    if cp_explicit:
        postal_code = cp_explicit.group(1)
    else:
        cp_tail = re.search(r"(?:,\s*|\s+)([A-Z]?\d{4})\s*$", raw, re.I)
        if cp_tail:
            postal_code = cp_tail.group(1)

    # Partes por coma
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    street = ""
    number = ""
    city = ""

    if parts:
        head = parts[0]
        num_match = re.search(r"^(.*?)[\s,]+(\d+[a-zA-Z]?)\s*$", head)
        if num_match:
            street = num_match.group(1).strip(" ,")
            number = num_match.group(2).strip()
        else:
            street = head
        # Ciudad: primera parte que no sea el head ni un CP puro
        for part in parts[1:]:
            compact = part.replace(" ", "")
            if re.fullmatch(r"[A-Z]?\d{4}", compact, re.I):
                if not postal_code:
                    postal_code = compact
                continue
            if re.fullmatch(r"(?:cp|codigo postal|código postal)\s*[A-Z]?\d{4}", part, re.I):
                continue
            city = part
            break
    else:
        street = raw

    # Si no hubo comas, intentar "... 6034 cordoba capital 5021"
    if not city:
        m = re.search(
            r"^(?P<street>.+?)\s+(?P<number>\d+[a-zA-Z]?)\s+(?P<city>.+?)(?:\s+(?P<cp>[A-Z]?\d{4}))?$",
            raw,
            re.I,
        )
        if m:
            street = m.group("street").strip(" ,")
            number = m.group("number")
            city = m.group("city").strip(" ,")
            if m.group("cp"):
                postal_code = m.group("cp")
            # sacar CP del final de city si quedó pegado
            city = re.sub(
                r"\s*(?:cp|codigo postal|código postal)?\s*[A-Z]?\d{4}\s*$",
                "",
                city,
                flags=re.I,
            ).strip(" ,")

    # Si el CP quedó igual a la altura, descartarlo (ej. tomó 6034 por error)
    if postal_code and number and postal_code.lstrip("XxYy") == number:
        # Buscar otro candidato al final del texto original
        candidates = re.findall(r"\b([A-Z]?\d{4})\b", raw, re.I)
        postal_code = ""
        for cand in reversed(candidates):
            if cand != number:
                postal_code = cand
                break

    city, province = _normalize_city_province(city, None)
    out = {
        "street": street,
        "number": number,
        "city": city,
        "postal_code": postal_code,
    }
    if province:
        out["province"] = province
    return {k: v for k, v in out.items() if v}


def resolve_zone_from_address(address: Dict[str, Any]) -> Dict[str, Any]:
    lat = address.get("lat")
    lon = address.get("lon")
    # lat/lon vacíos del bot ("", null) no cuentan
    try:
        if lat not in (None, "") and lon not in (None, ""):
            return build_zone_from_coords(float(lon), float(lat))
    except (TypeError, ValueError):
        pass

    street = (address.get("street") or "").strip()
    number = str(address.get("number") or "").strip()
    city = (address.get("city") or address.get("locality") or "").strip()
    postal_code = str(address.get("postal_code") or "").strip()
    province_name = (address.get("province") or address.get("province_name") or "").strip() or None

    # Frase completa en address / full_address / o street sin city
    freeform = (
        address.get("address")
        or address.get("full_address")
        or address.get("direccion")
        or ""
    ).strip()
    if (not street or not city) and freeform:
        parsed = parse_freeform_address(freeform)
        street = street or parsed.get("street", "")
        number = number or parsed.get("number", "")
        city = city or parsed.get("city", "")
        postal_code = postal_code or parsed.get("postal_code", "")
        province_name = province_name or parsed.get("province")

    if street and not city:
        # "rodolfo martinez 6034, cordoba capital, 5021" metido solo en street
        parsed = parse_freeform_address(street if not number else f"{street} {number}")
        if parsed.get("city"):
            street = parsed.get("street") or street
            number = number or parsed.get("number", "")
            city = parsed.get("city", "")
            postal_code = postal_code or parsed.get("postal_code", "")
            province_name = province_name or parsed.get("province")

    city, province_name = _normalize_city_province(city, province_name)

    # number pegado en street: "Rodolfo Martinez 6034"
    if street and not number:
        import re

        m = re.search(r"^(.*?)[\s,]+(\d+[a-zA-Z]?)\s*$", street)
        if m:
            street = m.group(1).strip(" ,")
            number = m.group(2).strip()

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
    # El bot a veces reusa la clave "id" (la que devuelve el catálogo) en vez de
    # "product_id" (la que espera esta tool). Aceptamos ambas.
    product_ids = [
        str(it.get("product_id") or it.get("id"))
        for it in items
        if it.get("product_id") or it.get("id")
    ]
    prices_map = _build_homepage_prices_map(product_ids, locality_id)
    lines = []
    subtotal = 0.0
    for it in items:
        pid = str(it.get("product_id") or it.get("id") or "")
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
    subcategory_id: Optional[str] = None,
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
            from routes.products import _descendant_category_ids_including_root

            cat_uuid = uuid.UUID(str(category_id))
            cat_ids = _descendant_category_ids_including_root(cat_uuid)
            query = query.filter(Product.category_id.in_(cat_ids))
        except (ValueError, TypeError):
            pass
    if subcategory_id:
        try:
            sub_uuid = uuid.UUID(str(subcategory_id))
            query = (
                query.join(ProductSubcategory, Product.id == ProductSubcategory.product_id)
                .filter(ProductSubcategory.subcategory_id == sub_uuid)
                .distinct()
            )
        except (ValueError, TypeError):
            pass

    pagination = query.order_by(Product.name.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    products = pagination.items
    ids = [str(p.id) for p in products]
    loc = _normalize_locality_id(locality_id)
    prices_map = _build_homepage_prices_map(ids, loc) if ids else {}
    catalog, _cid = catalog_for_locality(loc) if loc else (None, None)
    delivery = estimated_delivery_payload(catalog)

    items = []
    for p in products:
        info = prices_map.get(str(p.id)) or {}
        price_transfer = _positive_price(
            info.get("min_transfer_price"), info.get("min_price")
        )
        price_card = _positive_price(
            info.get("min_card_price"), info.get("min_price"), price_transfer
        )
        price = price_transfer or price_card
        # No devolver productos sin precio al bot (evita que arme listas con $0)
        if price is None:
            continue
        # Intencional: NO se incluyen price/price_label/price_transfer/price_card ni
        # main_image acá. Este endpoint es para que el bot liste nombres nada más;
        # precio real sale de build_full_quote (Cotizar Pedido) con zona resuelta,
        # y la foto solo se expone en product_detail (Detalle de Producto) cuando el
        # cliente la pide explícitamente para un producto puntual.
        items.append(
            {
                "id": str(p.id),
                "name": p.name,
                "description": (p.description or "")[:280] if p.description else None,
                "category_id": str(p.category_id) if p.category_id else None,
            }
        )

    return {
        "products": items,
        "estimated_delivery": delivery,
        "locality_id": loc,
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
    loc = _normalize_locality_id(locality_id)
    catalog, _cid = catalog_for_locality(loc) if loc else (None, None)
    # Intencional: NO se incluye precio acá. Esta es la única respuesta del bot que
    # trae main_image (foto), reservada para cuando el cliente la pide explícitamente
    # sobre un producto puntual; el precio real sale siempre de build_full_quote
    # (Cotizar Pedido) con la zona resuelta.
    return {
        "id": str(product.id),
        "name": product.name,
        "description": product.description,
        "category_id": str(product.category_id) if product.category_id else None,
        "main_image": product.get_main_image(),
        "estimated_delivery": estimated_delivery_payload(catalog),
        "locality_id": loc,
    }


MAX_QUOTE_ITEMS = 5


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
    if len(items) > MAX_QUOTE_ITEMS:
        raise ValueError(
            f"Estás mandando {len(items)} productos distintos en el mismo pedido, eso no es normal — "
            f"confirmá con el cliente cuál o cuáles productos puntuales quiere (máximo {MAX_QUOTE_ITEMS} "
            "por pedido) antes de volver a cotizar"
        )
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
