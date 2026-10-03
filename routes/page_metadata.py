from flask import Blueprint, request, jsonify, current_app
from database import db
from models.page_metadata import PageMetadata
from routes.admin import admin_required
from routes.redirects import normalize_path

page_metadata_bp = Blueprint("page_metadata", __name__)


@page_metadata_bp.route("/public/page-metadata", methods=["GET"])
def public_list_page_metadata():
    """Listado público de overrides activos: lo consume generateMetadata del frontend."""
    try:
        rows = PageMetadata.query.all()
        return jsonify(
            {
                "success": True,
                "data": [
                    {
                        "path": r.path,
                        "meta_title": r.meta_title,
                        "meta_description": r.meta_description,
                    }
                    for r in rows
                ],
            }
        ), 200
    except Exception as e:
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@page_metadata_bp.route("/admin/page-metadata", methods=["GET"])
@admin_required
def admin_list_page_metadata():
    try:
        rows = PageMetadata.query.order_by(PageMetadata.updated_at.desc()).all()
        return jsonify({"success": True, "data": [r.to_dict() for r in rows]}), 200
    except Exception as e:
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@page_metadata_bp.route("/admin/page-metadata/bulk-upsert", methods=["POST"])
@admin_required
def admin_bulk_upsert_page_metadata():
    """
    Body: {"items": [{"path", "page_type", "meta_title", "meta_description"}, ...]}
    Un item con meta_title y meta_description vacíos borra el override existente
    (vuelve a mostrar el valor automático/hardcodeado de la página).
    """
    try:
        data = request.get_json()
        if not data or not isinstance(data.get("items"), list):
            return jsonify({"success": False, "error": "Se requiere una lista de items"}), 400

        updated = 0
        cleared = 0

        for item in data["items"]:
            if not isinstance(item, dict):
                continue
            path = normalize_path(item.get("path", ""))
            if not path:
                continue
            page_type = (item.get("page_type") or "").strip() or "institutional"
            meta_title = (item.get("meta_title") or "").strip()
            meta_description = (item.get("meta_description") or "").strip()

            existing = PageMetadata.query.filter_by(path=path).first()

            if not meta_title and not meta_description:
                if existing:
                    db.session.delete(existing)
                    cleared += 1
                continue

            if existing:
                existing.page_type = page_type
                existing.meta_title = meta_title or None
                existing.meta_description = meta_description or None
                existing.updated_by = request.admin_user.id
            else:
                db.session.add(PageMetadata(
                    path=path,
                    page_type=page_type,
                    meta_title=meta_title or None,
                    meta_description=meta_description or None,
                    updated_by=request.admin_user.id,
                ))
            updated += 1

        db.session.commit()
        return jsonify({"success": True, "data": {"updated": updated, "cleared": cleared}}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500
