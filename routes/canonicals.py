from flask import Blueprint, request, jsonify, current_app
from database import db
from models.canonical_tag import CanonicalTag
from routes.admin import admin_required
from routes.redirects import normalize_path

canonicals_bp = Blueprint("canonicals", __name__)


@canonicals_bp.route("/public/canonicals", methods=["GET"])
def public_list_active_canonicals():
    """Listado público de overrides activos: lo consume generateMetadata del frontend."""
    try:
        rows = CanonicalTag.query.filter_by(is_active=True).all()
        return jsonify(
            {
                "success": True,
                "data": [
                    {"path": r.path, "canonical_url": r.canonical_url}
                    for r in rows
                ],
            }
        ), 200
    except Exception as e:
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@canonicals_bp.route("/admin/canonicals", methods=["GET"])
@admin_required
def admin_list_canonicals():
    try:
        rows = CanonicalTag.query.order_by(CanonicalTag.created_at.desc()).all()
        return jsonify({"success": True, "data": [r.to_dict() for r in rows]}), 200
    except Exception as e:
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@canonicals_bp.route("/admin/canonicals", methods=["POST"])
@admin_required
def admin_create_canonical():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Datos requeridos"}), 400

        path = normalize_path(data.get("path", ""))
        canonical_url = (data.get("canonical_url") or "").strip()

        if not path:
            return jsonify({"success": False, "error": "La URL de la página es obligatoria"}), 400
        if not canonical_url:
            return jsonify({"success": False, "error": "La URL canonical es obligatoria"}), 400
        if not canonical_url.startswith("/") and not canonical_url.startswith("http://") and not canonical_url.startswith("https://"):
            canonical_url = "/" + canonical_url

        if CanonicalTag.query.filter_by(path=path).first():
            return jsonify({"success": False, "error": "Ya existe un canonical para esa URL"}), 409

        tag = CanonicalTag(
            path=path,
            canonical_url=canonical_url,
            is_active=bool(data.get("is_active", True)),
            notes=(data.get("notes") or "").strip() or None,
        )
        db.session.add(tag)
        db.session.commit()
        return jsonify({"success": True, "data": tag.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@canonicals_bp.route("/admin/canonicals/<uuid:tag_id>", methods=["PUT"])
@admin_required
def admin_update_canonical(tag_id):
    try:
        tag = CanonicalTag.query.get(tag_id)
        if not tag:
            return jsonify({"success": False, "error": "No encontrado"}), 404
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Datos requeridos"}), 400

        new_path = tag.path
        if "path" in data:
            new_path = normalize_path(data.get("path", ""))
            if not new_path:
                return jsonify({"success": False, "error": "La URL de la página es obligatoria"}), 400

        new_canonical_url = tag.canonical_url
        if "canonical_url" in data:
            new_canonical_url = (data.get("canonical_url") or "").strip()
            if not new_canonical_url:
                return jsonify({"success": False, "error": "La URL canonical es obligatoria"}), 400
            if not new_canonical_url.startswith("/") and not new_canonical_url.startswith("http://") and not new_canonical_url.startswith("https://"):
                new_canonical_url = "/" + new_canonical_url

        if new_path != tag.path:
            existing = CanonicalTag.query.filter_by(path=new_path).first()
            if existing and existing.id != tag.id:
                return jsonify({"success": False, "error": "Ya existe un canonical para esa URL"}), 409

        tag.path = new_path
        tag.canonical_url = new_canonical_url

        if "is_active" in data:
            tag.is_active = bool(data["is_active"])
        if "notes" in data:
            tag.notes = (data.get("notes") or "").strip() or None

        db.session.commit()
        return jsonify({"success": True, "data": tag.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@canonicals_bp.route("/admin/canonicals/<uuid:tag_id>", methods=["DELETE"])
@admin_required
def admin_delete_canonical(tag_id):
    try:
        tag = CanonicalTag.query.get(tag_id)
        if not tag:
            return jsonify({"success": False, "error": "No encontrado"}), 404
        db.session.delete(tag)
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500
