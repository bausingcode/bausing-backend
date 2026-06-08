import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from database import db
from models.coupon import Coupon
from models.coupon_category_discount import CouponCategoryDiscount
from models.product import Product
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


def _parse_uuid(value):
    if value is None or value == "":
        return None
    try:
        return uuid.UUID(str(value).strip())
    except (ValueError, TypeError):
        return None


def _validate_category_discounts(raw_list):
    """
    Valida y parsea la lista de reglas de descuento por categoría.
    Cada regla debe tener category_id o subcategory_id (o ambos) y discount_value > 0.
    Devuelve (error_str, lista_parseada) o (None, lista).
    """
    if not isinstance(raw_list, list):
        return "category_discounts debe ser un array", None

    result = []
    for i, item in enumerate(raw_list):
        if not isinstance(item, dict):
            return f"category_discounts[{i}]: debe ser un objeto", None

        cat_id = _parse_uuid(item.get("category_id"))
        sub_id = _parse_uuid(item.get("subcategory_id"))

        if cat_id is None and sub_id is None:
            return (
                f"category_discounts[{i}]: debe tener category_id o subcategory_id",
                None,
            )

        try:
            dv = float(item.get("discount_value"))
        except (TypeError, ValueError):
            return f"category_discounts[{i}]: discount_value numérico requerido", None

        if dv <= 0 or dv > 100:
            return (
                f"category_discounts[{i}]: discount_value debe estar entre 0 y 100 (excluyendo 0)",
                None,
            )

        result.append({"category_id": cat_id, "subcategory_id": sub_id, "discount_value": dv})

    return None, result


def _sync_category_discounts(coupon: Coupon, rules: list):
    """Reemplaza las reglas de descuento por categoría del cupón."""
    # Eliminar las existentes
    CouponCategoryDiscount.query.filter_by(coupon_id=coupon.id).delete()
    # Insertar las nuevas
    for rule in rules:
        cd = CouponCategoryDiscount(
            coupon_id=coupon.id,
            category_id=rule["category_id"],
            subcategory_id=rule["subcategory_id"],
            discount_value=rule["discount_value"],
        )
        db.session.add(cd)


def _enrich_coupon_dict(c: Coupon) -> dict:
    """Convierte el cupón a dict y agrega product_name."""
    d = c.to_dict()
    if c.product_id:
        p = db.session.get(Product, c.product_id)
        d["product_name"] = p.name if p else None
    else:
        d["product_name"] = None
    return d


@coupons_bp.route("/api/coupons/preview", methods=["POST"])
@user_required
def preview_coupon_checkout():
    """
    Calcula el descuento esperado para el carrito actual (sin reservar el cupón).
    Requiere usuario autenticado (mismo criterio que crear orden).
    Aplica descuentos por categoría si el cupón los tiene configurados.
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

        # Cargar reglas de descuento por categoría si las hay
        cat_rules = CouponCategoryDiscount.query.filter_by(coupon_id=c.id).all()
        cat_rules_list = [r.to_dict() for r in cat_rules]

        # Si hay reglas por categoría, enriquecer cada línea con info de categoría del producto
        if cat_rules_list:
            from models.product import Product as ProductModel
            for line in disc_lines:
                try:
                    pid_uuid = _parse_uuid(line["product_id"])
                    if pid_uuid:
                        prod = db.session.get(ProductModel, pid_uuid)
                        if prod:
                            line["category_id"] = str(prod.category_id) if prod.category_id else None
                            line["subcategory_ids"] = [
                                str(a.subcategory_id)
                                for a in (prod.subcategory_associations or [])
                            ]
                except Exception:
                    pass

        club_ids = get_club_beneficios_product_id_set()
        total_disc, _discounts, cerr = compute_coupon_discount_amount(
            c, disc_lines, club_ids, cat_rules_list or None
        )
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
                        "product_id": str(c.product_id) if c.product_id else None,
                        "discount_type": c.discount_type,
                        "discount_value": float(c.discount_value)
                        if c.discount_value is not None
                        else 0.0,
                        "has_category_discounts": len(cat_rules_list) > 0,
                    },
                }
            ),
            200,
        )
    except Exception as e:
        current_app.logger.error("Error al validar cupón: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@coupons_bp.route("/admin/coupons", methods=["GET"])
@admin_required
def admin_list_coupons():
    """
    Lista cupones. Sin query: todos.
    ?club_beneficios_only=true  solo Club Beneficios
    ?club_beneficios_only=false solo generales
    ?product_id=<uuid>          solo cupones de ese producto
    """
    try:
        q = Coupon.query
        flag = _parse_bool_query(request.args.get("club_beneficios_only"))
        if flag is True:
            q = q.filter(Coupon.club_beneficios_only.is_(True))
        elif flag is False:
            q = q.filter(Coupon.club_beneficios_only.is_(False))
        raw_pid = request.args.get("product_id")
        if raw_pid:
            try:
                pid = uuid.UUID(raw_pid.strip())
                q = q.filter(Coupon.product_id == pid)
            except (ValueError, TypeError):
                pass
        rows = q.order_by(Coupon.created_at.desc()).all()
        coupons_data = [_enrich_coupon_dict(c) for c in rows]
        return jsonify({"success": True, "data": {"coupons": coupons_data}}), 200
    except Exception as e:
        current_app.logger.error("Error al listar cupones: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@coupons_bp.route("/admin/coupons", methods=["POST"])
@admin_required
def admin_create_coupon():
    """
    Alta de cupón. Para cupones club + percentage se pueden incluir category_discounts.
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

        product_id = None
        raw_pid = data.get("product_id")
        if raw_pid:
            try:
                product_id = uuid.UUID(str(raw_pid).strip())
                if not db.session.get(Product, product_id):
                    return jsonify({"success": False, "error": "Producto no encontrado"}), 400
            except (ValueError, TypeError):
                return jsonify({"success": False, "error": "product_id inválido"}), 400

        # Validar category_discounts si se envían
        raw_cat_discounts = data.get("category_discounts")
        cat_discount_rules = []
        if raw_cat_discounts:
            if not (bool(club_only) and discount_type == "percentage"):
                return jsonify(
                    {"success": False, "error": "category_discounts solo aplica a cupones Club Beneficios con descuento en porcentaje"}
                ), 400
            err, cat_discount_rules = _validate_category_discounts(raw_cat_discounts)
            if err:
                return jsonify({"success": False, "error": err}), 400

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
            product_id=product_id,
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(c)
        db.session.flush()  # obtener c.id antes de commit

        if cat_discount_rules:
            _sync_category_discounts(c, cat_discount_rules)

        db.session.commit()
        return jsonify({"success": True, "data": _enrich_coupon_dict(c)}), 201
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
        current_app.logger.error("Error al crear cupón: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


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

    if "product_id" in data:
        raw_pid = data.get("product_id")
        if raw_pid is None or raw_pid == "":
            out["product_id"] = None
        else:
            try:
                out["product_id"] = uuid.UUID(str(raw_pid).strip())
            except (ValueError, TypeError):
                return {"success": False, "error": "product_id inválido"}, None

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
        if "product_id" in fields:
            new_pid = fields["product_id"]
            if new_pid is not None and not db.session.get(Product, new_pid):
                return jsonify({"success": False, "error": "Producto no encontrado"}), 400
            c.product_id = new_pid

        # Procesar category_discounts si se incluyen en el payload
        if "category_discounts" in data:
            raw_cat = data["category_discounts"]
            is_club = fields.get("club_beneficios_only", c.club_beneficios_only)
            disc_type = fields.get("discount_type", c.discount_type)
            if raw_cat and not (is_club and str(disc_type).lower() == "percentage"):
                return jsonify(
                    {"success": False, "error": "category_discounts solo aplica a cupones Club Beneficios con descuento en porcentaje"}
                ), 400
            if raw_cat:
                cat_err, cat_rules = _validate_category_discounts(raw_cat)
                if cat_err:
                    return jsonify({"success": False, "error": cat_err}), 400
            else:
                cat_rules = []
            _sync_category_discounts(c, cat_rules)

        db.session.commit()
        return jsonify({"success": True, "data": _enrich_coupon_dict(c)}), 200
    except IntegrityError:
        db.session.rollback()
        return jsonify(
            {"success": False, "error": "Ya existe un cupón con ese código"}
        ), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error al actualizar cupón: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


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
        current_app.logger.error("Error al eliminar cupón: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500
