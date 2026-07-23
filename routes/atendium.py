# -*- coding: utf-8 -*-
"""
API Atendium — endpoints tool-oriented para el bot (catálogo, zona, quote, ventas, estado).
Prefijo: /atendium/v1
Auth: X-API-Key o Authorization Bearer (ATENDIUM_API_KEY o API_KEY).
"""
from __future__ import annotations

import uuid
from functools import wraps

from flask import Blueprint, jsonify, request

from config import Config
from database import db
from models.order import Order
from models.user import User
from routes.orders import create_order_for_user, order_to_dict
from services import atendium_commerce as commerce
from utils.crm_payment_methods import crm_medios_pago_id_for_checkout_method

atendium_bp = Blueprint("atendium", __name__)


def _ok(data=None, message="OK", http_status=200):
    body = {"status": True, "message": message}
    if data is not None:
        body["data"] = data
    return jsonify(body), http_status


def _err(message, http_status=400, data=None):
    body = {"status": False, "message": message}
    if data is not None:
        body["data"] = data
    return jsonify(body), http_status


def atendium_api_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = None
        if "X-API-Key" in request.headers:
            api_key = request.headers["X-API-Key"]
        elif "Authorization" in request.headers:
            auth = request.headers["Authorization"]
            api_key = auth.split(" ", 1)[1] if auth.startswith("Bearer ") else auth

        expected = Config.ATENDIUM_API_KEY or Config.API_KEY
        if not api_key or api_key != expected:
            return _err("Token inválido o no proporcionado", 401)
        return f(*args, **kwargs)

    return decorated


@atendium_bp.route("/health", methods=["GET"])
@atendium_api_key_required
def health():
    try:
        from sqlalchemy import text

        db.session.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"
    return _ok({"service": "atendium", "database": db_status})


@atendium_bp.route("/resolve-zone", methods=["POST"])
@atendium_api_key_required
def resolve_zone():
    data = request.get_json(silent=True) or {}
    try:
        zone = commerce.resolve_zone_from_address(data)
        return _ok(zone, "Zona resuelta")
    except ValueError as e:
        return _err(str(e), 400)
    except Exception as e:
        return _err(f"Error al resolver zona: {e}", 500)


@atendium_bp.route("/catalog", methods=["GET"])
@atendium_api_key_required
def catalog_search():
    try:
        result = commerce.search_products(
            q=request.args.get("q"),
            locality_id=request.args.get("locality_id"),
            category_id=request.args.get("category_id"),
            page=request.args.get("page", 1, type=int),
            per_page=request.args.get("per_page", 20, type=int),
        )
        return _ok(result)
    except Exception as e:
        return _err(f"Error al buscar catálogo: {e}", 500)


@atendium_bp.route("/catalog/<product_id>", methods=["GET"])
@atendium_api_key_required
def catalog_detail(product_id):
    try:
        detail = commerce.product_detail(product_id, request.args.get("locality_id"))
        return _ok(detail)
    except ValueError as e:
        return _err(str(e), 404)
    except Exception as e:
        return _err(f"Error al obtener producto: {e}", 500)


@atendium_bp.route("/validate-coupon", methods=["POST"])
@atendium_api_key_required
def validate_coupon():
    body = request.get_json(silent=True) or {}
    code = body.get("coupon_code") or body.get("code")
    items = body.get("items") or []
    if not code:
        return _err("coupon_code es requerido")
    if not isinstance(items, list) or not items:
        return _err("items es requerido (product_id, quantity, price)")

    # Si traen price, usarlo; si no, no se puede calcular sin localidad
    priced = []
    for it in items:
        pid = it.get("product_id")
        if not pid:
            continue
        try:
            qty = int(it.get("quantity") or 1)
            price = float(it.get("price") or it.get("unit_price") or 0)
        except (TypeError, ValueError):
            continue
        if qty < 1 or price <= 0:
            return _err(
                "Cada ítem necesita quantity>0 y price>0 "
                "(o usá /quote con locality para precios reales)"
            )
        priced.append(
            {
                "product_id": str(pid),
                "quantity": qty,
                "unit_price": price,
                "line_total": round(price * qty, 2),
            }
        )
    if not priced:
        return _err("No hay ítems válidos")

    try:
        discount, info = commerce.preview_coupon(code, priced)
        return _ok(
            {
                "valid": True,
                "coupon": info,
                "discount_amount": discount,
            },
            "Cupón válido",
        )
    except ValueError as e:
        return _err(str(e), 400, data={"valid": False})


@atendium_bp.route("/validate-referral", methods=["POST"])
@atendium_api_key_required
def validate_referral():
    body = request.get_json(silent=True) or {}
    code = body.get("referral_code") or body.get("code")
    if not code:
        return _err("referral_code es requerido")

    user_id = None
    email = (body.get("customer_email") or body.get("email") or "").strip().lower()
    if email:
        user = User.query.filter_by(email=email).first()
        if user:
            user_id = user.id

    try:
        normalized = commerce.validate_referral(code, user_id=user_id)
        return _ok({"valid": True, "referral_code": normalized}, "Código de referido válido")
    except ValueError as e:
        return _err(str(e), 400, data={"valid": False})


@atendium_bp.route("/quote", methods=["POST"])
@atendium_api_key_required
def quote():
    body = request.get_json(silent=True) or {}
    address = body.get("address") or body
    items = body.get("items")
    payment_method = body.get("payment_method") or "transfer"
    coupon_code = body.get("coupon_code")
    referral_code = body.get("referral_code")

    if not isinstance(items, list):
        return _err("items es requerido")

    user_id = None
    email = ((body.get("customer") or {}).get("email") or "").strip().lower()
    if email:
        u = User.query.filter_by(email=email).first()
        if u:
            user_id = u.id

    try:
        result = commerce.build_full_quote(
            address=address if body.get("address") else body,
            items=items,
            payment_method=payment_method,
            coupon_code=coupon_code,
            referral_code=referral_code,
            user_id=user_id,
        )
        msg = (
            "Cotización lista — requiere asesor"
            if result.get("requires_human_handoff")
            else "Cotización lista"
        )
        return _ok(result, msg)
    except ValueError as e:
        return _err(str(e), 400)
    except Exception as e:
        return _err(f"Error al cotizar: {e}", 500)


@atendium_bp.route("/orders", methods=["POST"])
@atendium_api_key_required
def create_order():
    body = request.get_json(silent=True) or {}
    customer = body.get("customer") or {}
    address = body.get("address") or {}
    items = body.get("items") or []
    payment_method = (body.get("payment_method") or "transfer").lower()
    coupon_code = body.get("coupon_code")
    referral_code = body.get("referral_code")

    if not customer or not address or not items:
        return _err("customer, address e items son requeridos")

    try:
        quote_data = commerce.build_full_quote(
            address=address,
            items=items,
            payment_method=payment_method,
            coupon_code=coupon_code,
            referral_code=referral_code,
        )
    except ValueError as e:
        return _err(str(e), 400)
    except Exception as e:
        return _err(f"Error al validar cotización: {e}", 500)

    if quote_data.get("requires_human_handoff"):
        return _err(
            quote_data.get("handoff_message")
            or "Esta venta debe completarla un asesor",
            409,
            data={
                "can_create_order": False,
                "requires_human_handoff": True,
                "handoff_reason": quote_data.get("handoff_reason"),
                "handoff_message": quote_data.get("handoff_message"),
                "whatsapp_phone": quote_data.get("whatsapp_phone"),
                "quote_summary": quote_data.get("quote_summary"),
                "estimated_delivery": quote_data.get("estimated_delivery"),
            },
        )

    # Revalidar total enviado por el bot (tolerancia 1 ARS)
    client_total = body.get("total")
    server_total = quote_data["total"]
    if client_total is not None:
        try:
            if abs(float(client_total) - float(server_total)) > 1.0:
                return _err(
                    f"total no coincide con la cotización del servidor "
                    f"(esperado {server_total}, recibido {client_total})",
                    400,
                    data={"expected_total": server_total, "quote": quote_data},
                )
        except (TypeError, ValueError):
            return _err("total inválido")

    try:
        user = commerce.find_or_create_user(customer)
    except ValueError as e:
        return _err(str(e), 400)
    except Exception as e:
        return _err(f"Error al crear/obtener usuario: {e}", 500)

    # Revalidar referido contra el user real (anti auto-referido)
    try:
        referral = commerce.validate_referral(referral_code, user_id=user.id)
    except ValueError as e:
        return _err(str(e), 400)

    zone = quote_data["zone"]
    priced_items = [
        {
            "product_id": line["product_id"],
            "quantity": line["quantity"],
            "price": line["unit_price"],
        }
        for line in quote_data["items"]
    ]

    medios_pago_id = crm_medios_pago_id_for_checkout_method(payment_method)
    observations = (body.get("observations") or "").strip()
    origin_note = "Origen: Atendium bot"
    observations = f"{observations}\n{origin_note}".strip() if observations else origin_note

    order_payload = {
        "customer": {
            "first_name": customer.get("first_name") or user.first_name,
            "last_name": customer.get("last_name") or user.last_name,
            "email": customer.get("email") or user.email,
            "phone": customer.get("phone") or user.phone,
            "alternate_phone": customer.get("alternate_phone"),
            "document_type": customer.get("document_type") or "DNI",
            "dni": customer.get("dni") or customer.get("document_number") or user.dni,
        },
        "address": {
            "street": address.get("street"),
            "number": address.get("number"),
            "floor": address.get("floor"),
            "apartment": address.get("apartment"),
            "city": address.get("city") or zone["locality"]["name"],
            "province_id": address.get("province_id"),
            "province": address.get("province") or address.get("province_name"),
            "postal_code": address.get("postal_code"),
            "references": address.get("references") or address.get("notes"),
        },
        "payment_method": payment_method,
        "pay_on_delivery": True,
        "crm_sale_type_id": body.get("crm_sale_type_id") or 1,
        "crm_zone_id": body.get("crm_zone_id") or zone.get("crm_zone_id"),
        "total": server_total,
        "payment_methods": [
            {
                "method": payment_method,
                "amount": server_total,
                "processed": False,
                "medios_pago_id": medios_pago_id,
            }
        ],
        "items": priced_items,
        "observations": observations,
        "coupon_code": (quote_data.get("coupon") or {}).get("code") or coupon_code,
        "referral_code": referral,
    }

    if not order_payload["address"].get("province_id") and address.get("province"):
        from models.province import Province

        prov = Province.query.filter(
            Province.name.ilike(f"%{address.get('province')}%")
        ).first()
        if prov:
            order_payload["address"]["province_id"] = str(prov.id)

    if not order_payload["address"].get("province_id"):
        return _err("address.province_id (o province) es requerido para crear la orden")

    try:
        resp = create_order_for_user(user, order_payload)
        body_resp, status = resp if isinstance(resp, tuple) else (resp, 201)
        data = body_resp.get_json(silent=True) if hasattr(body_resp, "get_json") else None
        if status >= 400 or not data or not data.get("success"):
            return _err(
                (data or {}).get("error") or "Error al crear la orden",
                status if status >= 400 else 400,
                data=data,
            )

        order_data = data.get("data") or data
        order_data["estimated_delivery"] = quote_data.get("estimated_delivery")
        order_data["can_create_order"] = True
        order_data["requires_human_handoff"] = False
        return _ok(order_data, "Orden creada", 201)
    except Exception as e:
        return _err(f"Error al crear orden: {e}", 500)


@atendium_bp.route("/orders", methods=["GET"])
@atendium_api_key_required
def list_orders():
    phone = request.args.get("phone")
    dni = request.args.get("dni")
    if not phone and not dni:
        return _err("phone o dni es requerido")

    matched_users = []
    if dni:
        matched_users = User.query.filter(User.dni == str(dni).strip()).all()

    if phone:
        digits = commerce.normalize_phone_digits(phone)
        phone_candidates = []
        if matched_users:
            phone_candidates = matched_users
        else:
            # Candidatos por coincidencia parcial (últimos dígitos) sin traer toda la tabla
            if len(digits) >= 8:
                tail = digits[-8:]
                phone_candidates = (
                    User.query.filter(User.phone.isnot(None), User.phone.contains(tail))
                    .limit(200)
                    .all()
                )
            if not phone_candidates:
                phone_candidates = User.query.filter(User.phone == phone).limit(50).all()
        matched_users = [u for u in phone_candidates if commerce.phones_match(u.phone, phone)]

    if not matched_users:
        return _ok({"orders": []}, "Sin pedidos para ese cliente")

    user_ids = [u.id for u in matched_users]
    limit = min(request.args.get("limit", 10, type=int), 50)
    orders = (
        Order.query.filter(Order.user_id.in_(user_ids))
        .order_by(Order.created_at.desc())
        .limit(limit)
        .all()
    )
    return _ok(
        {
            "orders": [
                {
                    "id": str(o.id),
                    "crm_order_id": o.crm_order_id,
                    "status": o.status,
                    "total": float(o.total) if o.total is not None else 0,
                    "payment_method": o.payment_method,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                    "estimated_delivery": commerce.estimated_delivery_payload(o.catalog)
                    if o.catalog
                    else None,
                }
                for o in orders
            ]
        }
    )


@atendium_bp.route("/orders/<order_id>", methods=["GET"])
@atendium_api_key_required
def get_order(order_id):
    phone = request.args.get("phone")
    if not phone:
        return _err("phone es requerido para validar el cliente")

    order = None
    try:
        order = Order.query.filter_by(id=uuid.UUID(order_id)).first()
    except ValueError:
        try:
            order = Order.query.filter_by(crm_order_id=int(order_id)).first()
        except ValueError:
            return _err("ID de orden inválido (UUID o crm_order_id)")

    if not order:
        return _err("Orden no encontrada", 404)

    user = User.query.get(order.user_id)
    if not user or not commerce.phones_match(user.phone, phone):
        return _err("Orden no encontrada para ese teléfono", 404)

    try:
        data = order_to_dict(order)
    except Exception:
        data = order.to_dict()

    data["crm_order_id"] = order.crm_order_id
    data["estimated_delivery"] = commerce.estimated_delivery_payload(order.catalog)
    return _ok(data)
