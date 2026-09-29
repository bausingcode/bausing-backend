from flask import Blueprint, request, jsonify, current_app
from database import db
from models.category_faq_item import CategoryFaqItem
from routes.admin import admin_required
import uuid as uuid_lib

category_faq_items_bp = Blueprint("category_faq_items", __name__)


def _parse_uuid(raw):
    try:
        return uuid_lib.UUID(str(raw))
    except (ValueError, TypeError):
        return None


@category_faq_items_bp.route("/public/category-faq-items", methods=["GET"])
def public_list_category_faq_items():
    """Listado público: solo publicadas de una categoría, orden por sort_order."""
    try:
        category_id = _parse_uuid(request.args.get("category_id", ""))
        if not category_id:
            return jsonify({"success": False, "error": "category_id inválido"}), 400

        rows = (
            CategoryFaqItem.query.filter_by(category_id=category_id, is_published=True)
            .order_by(CategoryFaqItem.sort_order.asc(), CategoryFaqItem.created_at.asc())
            .all()
        )
        return jsonify(
            {
                "success": True,
                "data": [
                    {"id": str(r.id), "question": r.question, "answer": r.answer}
                    for r in rows
                ],
            }
        ), 200
    except Exception as e:
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@category_faq_items_bp.route("/admin/category-faq-items", methods=["GET"])
@admin_required
def admin_list_category_faq_items():
    try:
        query = CategoryFaqItem.query
        category_id = request.args.get("category_id")
        if category_id:
            parsed = _parse_uuid(category_id)
            if not parsed:
                return jsonify({"success": False, "error": "category_id inválido"}), 400
            query = query.filter_by(category_id=parsed)

        rows = query.order_by(
            CategoryFaqItem.category_id.asc(),
            CategoryFaqItem.sort_order.asc(),
            CategoryFaqItem.created_at.asc(),
        ).all()
        return jsonify({"success": True, "data": [r.to_dict() for r in rows]}), 200
    except Exception as e:
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@category_faq_items_bp.route("/admin/category-faq-items", methods=["POST"])
@admin_required
def admin_create_category_faq_item():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Datos requeridos"}), 400

        category_id = _parse_uuid(data.get("category_id", ""))
        q = (data.get("question") or "").strip()
        a = (data.get("answer") or "").strip()
        if not category_id:
            return jsonify({"success": False, "error": "La categoría es obligatoria"}), 400
        if not q or not a:
            return jsonify(
                {"success": False, "error": "Pregunta y respuesta son obligatorias"}
            ), 400

        max_order = (
            db.session.query(db.func.max(CategoryFaqItem.sort_order))
            .filter(CategoryFaqItem.category_id == category_id)
            .scalar()
        )
        next_order = (max_order or 0) + 1

        item = CategoryFaqItem(
            category_id=category_id,
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


@category_faq_items_bp.route("/admin/category-faq-items/<uuid:item_id>", methods=["PUT"])
@admin_required
def admin_update_category_faq_item(item_id):
    try:
        item = CategoryFaqItem.query.get(item_id)
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


@category_faq_items_bp.route("/admin/category-faq-items/<uuid:item_id>", methods=["DELETE"])
@admin_required
def admin_delete_category_faq_item(item_id):
    try:
        item = CategoryFaqItem.query.get(item_id)
        if not item:
            return jsonify({"success": False, "error": "No encontrado"}), 404
        db.session.delete(item)
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@category_faq_items_bp.route("/admin/category-faq-items/reorder", methods=["PUT"])
@admin_required
def admin_reorder_category_faq_items():
    """Body: { "category_id": "uuid", "ordered_ids": ["uuid", ...] } — orden dentro de esa categoría."""
    try:
        data = request.get_json()
        if not data or not isinstance(data.get("ordered_ids"), list):
            return jsonify(
                {"success": False, "error": "Se requiere ordered_ids (lista de UUID)"}
            ), 400

        category_id = _parse_uuid(data.get("category_id", ""))
        if not category_id:
            return jsonify({"success": False, "error": "category_id inválido"}), 400

        ordered = []
        for raw in data["ordered_ids"]:
            parsed = _parse_uuid(raw)
            if not parsed:
                return jsonify({"success": False, "error": f"ID inválido: {raw}"}), 400
            ordered.append(parsed)

        if not ordered:
            return jsonify({"success": True, "data": []}), 200

        items = CategoryFaqItem.query.filter(
            CategoryFaqItem.id.in_(ordered), CategoryFaqItem.category_id == category_id
        ).all()
        by_id = {i.id: i for i in items}
        for pos, uid in enumerate(ordered):
            row = by_id.get(uid)
            if row:
                row.sort_order = pos

        db.session.commit()
        rows = (
            CategoryFaqItem.query.filter_by(category_id=category_id)
            .order_by(CategoryFaqItem.sort_order.asc(), CategoryFaqItem.created_at.asc())
            .all()
        )
        return jsonify({"success": True, "data": [r.to_dict() for r in rows]}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error interno: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500
