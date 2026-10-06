from flask import Blueprint, request, jsonify, current_app

from database import db
from models.creator_program_content import CreatorProgramContent, DEFAULT_CREATOR_PROGRAM_CONTENT
from routes.admin import admin_required

creator_program_bp = Blueprint("creator_program", __name__)

_STRING_FIELDS = [
    "hero_title",
    "hero_subtitle",
    "hero_description",
    "steps_title",
    "requirements_title",
    "requirements_note",
    "join_title",
    "join_description",
    "whatsapp_number",
    "whatsapp_message",
    "join_followup",
    "benefits_title",
    "cta_title",
    "cta_button_text",
]

_LIST_FIELDS = ["steps", "requirements", "benefits"]


def _normalize_content(data):
    merged = dict(DEFAULT_CREATOR_PROGRAM_CONTENT)

    for field in _STRING_FIELDS:
        if field in data and data[field] is not None:
            value = str(data[field]).strip()
            if value:
                merged[field] = value

    for field in _LIST_FIELDS:
        if field in data and isinstance(data[field], list):
            items = [str(item).strip() for item in data[field] if str(item).strip()]
            if items:
                merged[field] = items

    return merged


@creator_program_bp.route("/public/creator-program", methods=["GET"])
def public_get_creator_program():
    try:
        row = CreatorProgramContent.get_singleton()
        return jsonify({"success": True, "data": row.to_dict()}), 200
    except Exception as e:
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@creator_program_bp.route("/admin/creator-program", methods=["GET"])
@admin_required
def admin_get_creator_program():
    try:
        row = CreatorProgramContent.get_singleton()
        return jsonify({"success": True, "data": row.to_dict()}), 200
    except Exception as e:
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@creator_program_bp.route("/admin/creator-program", methods=["PUT"])
@admin_required
def admin_save_creator_program():
    try:
        data = request.get_json()
        if not data or not isinstance(data, dict):
            return jsonify({"success": False, "error": "Datos requeridos"}), 400

        row = CreatorProgramContent.get_singleton()
        row.content = _normalize_content(data)
        row.updated_by = request.admin_user.id
        db.session.commit()

        return jsonify({"success": True, "data": row.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500
