from flask import Blueprint, request, jsonify, current_app
from database import db
from models.faq_item import FaqItem
from routes.admin import admin_required
import uuid as uuid_lib

faq_items_bp = Blueprint("faq_items", __name__)


@faq_items_bp.route("/public/faq-items", methods=["GET"])
def public_list_faq_items():
    """Listado público: solo publicadas, orden por sort_order."""
    try:
        rows = (
            FaqItem.query.filter_by(is_published=True)
            .order_by(FaqItem.sort_order.asc(), FaqItem.created_at.asc())
            .all()
        )
        return jsonify(
            {
                "success": True,
                "data": [
                    {
                        "id": str(r.id),
                        "question": r.question,
                        "answer": r.answer,
                    }
                    for r in rows
                ],
            }
        ), 200
    except Exception as e:
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@faq_items_bp.route("/admin/faq-items", methods=["GET"])
@admin_required
def admin_list_faq_items():
    try:
        rows = FaqItem.query.order_by(FaqItem.sort_order.asc(), FaqItem.created_at.asc()).all()
        return jsonify({"success": True, "data": [r.to_dict() for r in rows]}), 200
    except Exception as e:
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@faq_items_bp.route("/admin/faq-items", methods=["POST"])
@admin_required
def admin_create_faq_item():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Datos requeridos"}), 400
        q = (data.get("question") or "").strip()
        a = (data.get("answer") or "").strip()
        if not q or not a:
            return jsonify(
                {"success": False, "error": "Pregunta y respuesta son obligatorias"}
            ), 400

        max_order = db.session.query(db.func.max(FaqItem.sort_order)).scalar()
        next_order = (max_order or 0) + 1

        item = FaqItem(
            question=q,
            answer=a,
            sort_order=int(data.get("sort_order", next_order)),
            is_published=bool(data.get("is_published", True)),
        )
        db.session.add(item)
        db.session.commit()
        return jsonify({"success": True, "data": item.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@faq_items_bp.route("/admin/faq-items/<uuid:item_id>", methods=["PUT"])
@admin_required
def admin_update_faq_item(item_id):
    try:
        item = FaqItem.query.get(item_id)
        if not item:
            return jsonify({"success": False, "error": "No encontrado"}), 404
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Datos requeridos"}), 400

        if "question" in data:
            q = (data.get("question") or "").strip()
            if not q:
                return jsonify({"success": False, "error": "La pregunta no puede estar vacía"}), 400
            item.question = q
        if "answer" in data:
            a = (data.get("answer") or "").strip()
            if not a:
                return jsonify({"success": False, "error": "La respuesta no puede estar vacía"}), 400
            item.answer = a
        if "sort_order" in data and data["sort_order"] is not None:
            item.sort_order = int(data["sort_order"])
        if "is_published" in data:
            item.is_published = bool(data["is_published"])

        db.session.commit()
        return jsonify({"success": True, "data": item.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@faq_items_bp.route("/admin/faq-items/<uuid:item_id>", methods=["DELETE"])
@admin_required
def admin_delete_faq_item(item_id):
    try:
        item = FaqItem.query.get(item_id)
        if not item:
            return jsonify({"success": False, "error": "No encontrado"}), 404
        db.session.delete(item)
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@faq_items_bp.route("/admin/faq-items/reorder", methods=["PUT"])
@admin_required
def admin_reorder_faq_items():
    """Body: { \"ordered_ids\": [\"uuid\", ...] } — define el orden completo."""
    try:
        data = request.get_json()
        if not data or not isinstance(data.get("ordered_ids"), list):
            return jsonify(
                {"success": False, "error": "Se requiere ordered_ids (lista de UUID)"}
            ), 400

        ordered = []
        for raw in data["ordered_ids"]:
            try:
                ordered.append(uuid_lib.UUID(str(raw)))
            except (ValueError, TypeError):
                return jsonify({"success": False, "error": f"ID inválido: {raw}"}), 400

        if not ordered:
            return jsonify({"success": True, "data": []}), 200

        items = FaqItem.query.filter(FaqItem.id.in_(ordered)).all()
        by_id = {i.id: i for i in items}
        for pos, uid in enumerate(ordered):
            row = by_id.get(uid)
            if row:
                row.sort_order = pos

        db.session.commit()
        rows = FaqItem.query.order_by(FaqItem.sort_order.asc(), FaqItem.created_at.asc()).all()
        return jsonify({"success": True, "data": [r.to_dict() for r in rows]}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500
