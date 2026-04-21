from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from database import db
from models.coupon import Coupon
from routes.admin import admin_required
from routes.auth import user_required

coupons_bp = Blueprint("coupons", __name__)


def _parse_dt(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _normalize_code(raw):
    if raw is None:
        return ""
    return str(raw).strip().upper()


def _parse_bool_query(raw):
    if raw is None or raw == "":
        return None
    s = str(raw).strip().lower()
    if s in ("1", "true", "yes"):
        return True
    if s in ("0", "false", "no"):
        return False
    return None


@coupons_bp.route("/api/coupons/preview", methods=["POST"])
@user_required
def preview_coupon_checkout():
    """
    Calcula el descuento esperado para el carrito actual (sin reservar el cupón).
    Requiere usuario autenticado (mismo criterio que crear orden).
    """
    from utils.coupon_order import (
        compute_coupon_discount_amount,
        get_club_beneficios_product_id_set,
        normalize_coupon_code,
        validate_coupon_row,
    )

    try:
        body = request.get_json() or {}
        code = normalize_coupon_code(body.get("code") or body.get("coupon_code"))
        if not code:
            return jsonify({"success": False, "error": "Código de cupón requerido"}), 400
        items = body.get("items")
        if not isinstance(items, list) or len(items) == 0:
            return jsonify({"success": False, "error": "items es requerido"}), 400

        c = Coupon.query.filter(func.lower(Coupon.code) == code.lower()).first()
        if not c:
            return jsonify({"success": False, "error": "Cupón no encontrado"}), 400
        vmsg = validate_coupon_row(c)
        if vmsg:
            return jsonify({"success": False, "error": vmsg}), 400

        disc_lines = []
        for it in items:
            pid = it.get("product_id")
            if not pid:
                continue
            try:
                price = float(it.get("price", 0))
                qty = int(it.get("quantity", 1))
            except (TypeError, ValueError):
                continue
            if price <= 0 or qty <= 0:
                continue
            disc_lines.append(
                {
                    "product_id": pid,
                    "precio_total_original": price * qty,
                }
            )

        if not disc_lines:
            return jsonify(
                {"success": False, "error": "No hay líneas válidas para calcular el descuento"}
            ), 400

        club_ids = get_club_beneficios_product_id_set()
        total_disc, _discounts, cerr = compute_coupon_discount_amount(c, disc_lines, club_ids)
        if cerr:
            return jsonify({"success": False, "error": cerr}), 400

        return (
            jsonify(
                {
                    "success": True,
                    "data": {
                        "code": c.code,
                        "discount_amount": round(float(total_disc), 2),
                        "club_beneficios_only": bool(c.club_beneficios_only),
                        "discount_type": c.discount_type,
                        "discount_value": float(c.discount_value)
                        if c.discount_value is not None
                        else 0.0,
                    },
                }
            ),
            200,
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@coupons_bp.route("/admin/coupons", methods=["GET"])
@admin_required
def admin_list_coupons():
    """
    Lista cupones. Sin query: todos.
    ?club_beneficios_only=true  solo Club Beneficios
    ?club_beneficios_only=false solo generales
    """
    try:
        q = Coupon.query
        flag = _parse_bool_query(request.args.get("club_beneficios_only"))
        if flag is True:
            q = q.filter(Coupon.club_beneficios_only.is_(True))
        elif flag is False:
            q = q.filter(Coupon.club_beneficios_only.is_(False))
        rows = q.order_by(Coupon.created_at.desc()).all()
        return jsonify(
            {"success": True, "data": {"coupons": [c.to_dict() for c in rows]}}
        ), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@coupons_bp.route("/admin/coupons", methods=["POST"])
@admin_required
def admin_create_coupon():
    """
    Alta de cupón general o exclusivo Club Beneficios (club_beneficios_only, default false).
    """
    try:
        data = request.get_json() or {}
        code = _normalize_code(data.get("code"))
        if not code or len(code) > 64:
            return jsonify(
                {"success": False, "error": "Código inválido (1–64 caracteres)"}
            ), 400

        dup = (
            Coupon.query.filter(func.lower(Coupon.code) == code.lower())
            .with_entities(Coupon.id)
            .first()
        )
        if dup:
            return jsonify(
                {"success": False, "error": "Ya existe un cupón con ese código"}
            ), 400

        discount_type = (data.get("discount_type") or "percentage").strip().lower()
        if discount_type not in ("percentage", "fixed"):
            return jsonify(
                {"success": False, "error": 'discount_type debe ser "percentage" o "fixed"'}
            ), 400

        try:
            discount_value = float(data.get("discount_value"))
        except (TypeError, ValueError):
            return jsonify(
                {"success": False, "error": "discount_value numérico requerido"}
            ), 400

        if discount_value <= 0:
            return jsonify(
                {"success": False, "error": "El descuento debe ser mayor a 0"}
            ), 400
        if discount_type == "percentage" and discount_value > 100:
            return jsonify(
                {"success": False, "error": "Porcentaje no puede superar 100"}
            ), 400

        max_uses = data.get("max_uses")
        if max_uses is not None and max_uses != "":
            try:
                max_uses = int(max_uses)
                if max_uses < 1:
                    raise ValueError()
            except (TypeError, ValueError):
                return jsonify(
                    {"success": False, "error": "max_uses debe ser entero >= 1 o vacío"}
                ), 400
        else:
            max_uses = None

        valid_from = _parse_dt(data.get("valid_from"))
        valid_until = _parse_dt(data.get("valid_until"))
        if valid_from and valid_until and valid_until < valid_from:
            return jsonify(
                {"success": False, "error": "valid_until debe ser posterior a valid_from"}
            ), 400

        is_active = data.get("is_active", True)
        if isinstance(is_active, str):
            is_active = is_active.lower() in ("1", "true", "yes")

        club_only = data.get("club_beneficios_only", False)
        if isinstance(club_only, str):
            club_only = club_only.lower() in ("1", "true", "yes")

        c = Coupon(
            code=code,
            discount_type=discount_type,
            discount_value=discount_value,
            max_uses=max_uses,
            uses_count=0,
            valid_from=valid_from,
            valid_until=valid_until,
            is_active=bool(is_active),
            club_beneficios_only=bool(club_only),
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(c)
        db.session.commit()
        return jsonify({"success": True, "data": c.to_dict()}), 201
    except IntegrityError:
        db.session.rollback()
        return jsonify(
            {"success": False, "error": "Ya existe un cupón con ese código"}
        ), 400
    except ValueError as e:
        db.session.rollback()
        return jsonify({"success": False, "error": f"Fecha inválida: {e}"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


def _validate_coupon_fields(data, *, require_code=False):
    """Valida campos comunes create/update. Devuelve (error_dict, None) o (None, values_dict)."""
    out = {}
    if require_code or data.get("code") is not None:
        code = _normalize_code(data.get("code"))
        if not code or len(code) > 64:
            return {"success": False, "error": "Código inválido (1–64 caracteres)"}, None
        out["code"] = code

    if "discount_type" in data or require_code:
        discount_type = (data.get("discount_type") or "percentage").strip().lower()
        if discount_type not in ("percentage", "fixed"):
            return {
                "success": False,
                "error": 'discount_type debe ser "percentage" o "fixed"',
            }, None
        out["discount_type"] = discount_type

    if "discount_value" in data or require_code:
        try:
            discount_value = float(data.get("discount_value"))
        except (TypeError, ValueError):
            return {"success": False, "error": "discount_value numérico requerido"}, None
        if discount_value <= 0:
            return {"success": False, "error": "El descuento debe ser mayor a 0"}, None
        dt = out.get("discount_type") or (data.get("discount_type") or "percentage")
        if str(dt).lower() == "percentage" and discount_value > 100:
            return {"success": False, "error": "Porcentaje no puede superar 100"}, None
        out["discount_value"] = discount_value

    max_uses = data.get("max_uses")
    if "max_uses" in data:
        if max_uses is None or max_uses == "":
            out["max_uses"] = None
        else:
            try:
                mu = int(max_uses)
                if mu < 1:
                    raise ValueError()
                out["max_uses"] = mu
            except (TypeError, ValueError):
                return {
                    "success": False,
                    "error": "max_uses debe ser entero >= 1 o vacío",
                }, None

    if "valid_from" in data:
        try:
            out["valid_from"] = _parse_dt(data.get("valid_from"))
        except ValueError as e:
            return {"success": False, "error": f"Fecha inválida (desde): {e}"}, None
    if "valid_until" in data:
        try:
            out["valid_until"] = _parse_dt(data.get("valid_until"))
        except ValueError as e:
            return {"success": False, "error": f"Fecha inválida (hasta): {e}"}, None

    if "is_active" in data:
        ia = data.get("is_active")
        if isinstance(ia, str):
            ia = ia.lower() in ("1", "true", "yes")
        out["is_active"] = bool(ia)

    if "club_beneficios_only" in data:
        co = data.get("club_beneficios_only")
        if isinstance(co, str):
            co = co.lower() in ("1", "true", "yes")
        out["club_beneficios_only"] = bool(co)

    return None, out


@coupons_bp.route("/admin/coupons/<uuid:coupon_id>", methods=["PUT"])
@admin_required
def admin_update_coupon(coupon_id):
    try:
        c = db.session.get(Coupon, coupon_id)
        if not c:
            return jsonify({"success": False, "error": "Cupón no encontrado"}), 404

        data = request.get_json() or {}
        err, fields = _validate_coupon_fields(data, require_code=True)
        if err:
            return jsonify(err), 400

        vf = fields["valid_from"] if "valid_from" in fields else c.valid_from
        vt = fields["valid_until"] if "valid_until" in fields else c.valid_until
        if vf and vt and vt < vf:
            return jsonify(
                {
                    "success": False,
                    "error": "valid_until debe ser posterior a valid_from",
                }
            ), 400

        new_code = fields["code"]
        other = (
            Coupon.query.filter(
                func.lower(Coupon.code) == new_code.lower(),
                Coupon.id != c.id,
            )
            .first()
        )
        if other:
            return jsonify(
                {"success": False, "error": "Ya existe un cupón con ese código"}
            ), 400

        new_max = fields.get("max_uses", c.max_uses)
        if new_max is not None and int(c.uses_count or 0) > new_max:
            return jsonify(
                {
                    "success": False,
                    "error": "max_uses no puede ser menor a los usos ya registrados",
                }
            ), 400

        c.code = new_code
        c.discount_type = fields.get("discount_type", c.discount_type)
        c.discount_value = fields.get("discount_value", c.discount_value)
        if "max_uses" in fields:
            c.max_uses = fields["max_uses"]
        if "valid_from" in fields:
            c.valid_from = fields["valid_from"]
        if "valid_until" in fields:
            c.valid_until = fields["valid_until"]
        if "is_active" in fields:
            c.is_active = fields["is_active"]
        if "club_beneficios_only" in fields:
            c.club_beneficios_only = fields["club_beneficios_only"]

        db.session.commit()
        return jsonify({"success": True, "data": c.to_dict()}), 200
    except IntegrityError:
        db.session.rollback()
        return jsonify(
            {"success": False, "error": "Ya existe un cupón con ese código"}
        ), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@coupons_bp.route("/admin/coupons/<uuid:coupon_id>", methods=["DELETE"])
@admin_required
def admin_delete_coupon(coupon_id):
    try:
        c = db.session.get(Coupon, coupon_id)
        if not c:
            return jsonify({"success": False, "error": "Cupón no encontrado"}), 404
        db.session.delete(c)
        db.session.commit()
        return jsonify({"success": True, "message": "Eliminado"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
