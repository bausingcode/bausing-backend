from flask import Blueprint, request, jsonify, current_app
from database import db
from models.redirect_rule import RedirectRule
from routes.admin import admin_required

redirects_bp = Blueprint("redirects", __name__)


def normalize_path(raw: str) -> str:
    """Normaliza a un pathname relativo: sin dominio, sin query/hash, empieza con '/'."""
    value = (raw or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        value = value.split("://", 1)[1]
        slash_idx = value.find("/")
        value = value[slash_idx:] if slash_idx != -1 else "/"
    if not value.startswith("/"):
        value = "/" + value
    value = value.split("?", 1)[0].split("#", 1)[0]
    if len(value) > 1 and value.endswith("/"):
        value = value.rstrip("/")
    return value or "/"


@redirects_bp.route("/public/redirects", methods=["GET"])
def public_list_active_redirects():
    """Listado público de reglas activas: lo consume el middleware del frontend."""
    try:
        rows = RedirectRule.query.filter_by(is_active=True).all()
        return jsonify(
            {
                "success": True,
                "data": [
                    {
                        "source_path": r.source_path,
                        "target_path": r.target_path,
                        "redirect_type": r.redirect_type,
                    }
                    for r in rows
                ],
            }
        ), 200
    except Exception as e:
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@redirects_bp.route("/public/redirects/hit", methods=["POST"])
def public_register_redirect_hit():
    """Incrementa el contador de uso de una regla. Best-effort, no bloquea el redirect."""
    try:
        data = request.get_json(silent=True) or {}
        source_path = normalize_path(data.get("source_path", ""))
        if not source_path:
            return jsonify({"success": False, "error": "source_path requerido"}), 400
        rule = RedirectRule.query.filter_by(source_path=source_path, is_active=True).first()
        if rule:
            rule.hit_count = (rule.hit_count or 0) + 1
            db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@redirects_bp.route("/admin/redirects", methods=["GET"])
@admin_required
def admin_list_redirects():
    try:
        rows = RedirectRule.query.order_by(RedirectRule.created_at.desc()).all()
        return jsonify({"success": True, "data": [r.to_dict() for r in rows]}), 200
    except Exception as e:
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@redirects_bp.route("/admin/redirects", methods=["POST"])
@admin_required
def admin_create_redirect():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Datos requeridos"}), 400

        source = normalize_path(data.get("source_path", ""))
        target = (data.get("target_path") or "").strip()
        redirect_type = int(data.get("redirect_type", 301))

        if not source:
            return jsonify({"success": False, "error": "La URL de origen es obligatoria"}), 400
        if not target:
            return jsonify({"success": False, "error": "La URL de destino es obligatoria"}), 400
        if redirect_type not in (301, 302):
            return jsonify({"success": False, "error": "redirect_type debe ser 301 o 302"}), 400
        if not target.startswith("/") and not target.startswith("http://") and not target.startswith("https://"):
            target = "/" + target
        if source == normalize_path(target):
            return jsonify({"success": False, "error": "El origen y el destino no pueden ser la misma URL"}), 400

        if RedirectRule.query.filter_by(source_path=source).first():
            return jsonify({"success": False, "error": "Ya existe un redirect para esa URL de origen"}), 409

        rule = RedirectRule(
            source_path=source,
            target_path=target,
            redirect_type=redirect_type,
            is_active=bool(data.get("is_active", True)),
            notes=(data.get("notes") or "").strip() or None,
        )
        db.session.add(rule)
        db.session.commit()
        return jsonify({"success": True, "data": rule.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@redirects_bp.route("/admin/redirects/<uuid:rule_id>", methods=["PUT"])
@admin_required
def admin_update_redirect(rule_id):
    try:
        rule = RedirectRule.query.get(rule_id)
        if not rule:
            return jsonify({"success": False, "error": "No encontrado"}), 404
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Datos requeridos"}), 400

        new_source = rule.source_path
        if "source_path" in data:
            new_source = normalize_path(data.get("source_path", ""))
            if not new_source:
                return jsonify({"success": False, "error": "La URL de origen es obligatoria"}), 400

        new_target = rule.target_path
        if "target_path" in data:
            new_target = (data.get("target_path") or "").strip()
            if not new_target:
                return jsonify({"success": False, "error": "La URL de destino es obligatoria"}), 400
            if not new_target.startswith("/") and not new_target.startswith("http://") and not new_target.startswith("https://"):
                new_target = "/" + new_target

        if new_source == normalize_path(new_target):
            return jsonify({"success": False, "error": "El origen y el destino no pueden ser la misma URL"}), 400

        if new_source != rule.source_path:
            existing = RedirectRule.query.filter_by(source_path=new_source).first()
            if existing and existing.id != rule.id:
                return jsonify({"success": False, "error": "Ya existe un redirect para esa URL de origen"}), 409

        rule.source_path = new_source
        rule.target_path = new_target

        if "redirect_type" in data:
            redirect_type = int(data["redirect_type"])
            if redirect_type not in (301, 302):
                return jsonify({"success": False, "error": "redirect_type debe ser 301 o 302"}), 400
            rule.redirect_type = redirect_type
        if "is_active" in data:
            rule.is_active = bool(data["is_active"])
        if "notes" in data:
            rule.notes = (data.get("notes") or "").strip() or None

        db.session.commit()
        return jsonify({"success": True, "data": rule.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@redirects_bp.route("/admin/redirects/<uuid:rule_id>", methods=["DELETE"])
@admin_required
def admin_delete_redirect(rule_id):
    try:
        rule = RedirectRule.query.get(rule_id)
        if not rule:
            return jsonify({"success": False, "error": "No encontrado"}), 404
        db.session.delete(rule)
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500
