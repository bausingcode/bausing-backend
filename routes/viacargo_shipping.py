# -*- coding: utf-8 -*-
import os
import re
import uuid
import logging
from decimal import Decimal

from flask import Blueprint, jsonify, request

from models.product import Product
from services.viacargo_busplus import build_payload_strings, cotizar_busplus_payload

logger = logging.getLogger(__name__)

viacargo_shipping_bp = Blueprint("viacargo_shipping", __name__)

MSG_CP_NO_DISPONIBLE_ENVIO = "Este código postal no tiene envío disponible."
MSG_CP_INVALIDO = "Por favor, ingresá un código postal válido."


def _user_facing_cotizar_error(err: str, bus_http) -> str:
    """Mensaje amable si Busplus/validación indica CP inválido o sin cobertura."""
    if not err:
        return MSG_CP_NO_DISPONIBLE_ENVIO
    el = (err or "").lower()
    # CP con formato inválido
    if "codigo postal no val" in el or "postal no val" in el:
        return MSG_CP_INVALIDO
    # Sin cobertura: CP válido pero sin servicio, producto no encontrado, timeout, etc.
    if (
        "codigo postal" in el
        or "código postal" in el
        or "no se encontró el producto" in el
        or "not found" in el
        or "sin cobertura" in el
        or "no cubre" in el
        or bus_http in (400, 404)
        or bus_http is None  # timeout / error de red
    ):
        return MSG_CP_NO_DISPONIBLE_ENVIO
    return err


def _norm_cp_busplus(value: str) -> str:
    """
    CP para la API Alerce/Busplus: clásico de 4 dígitos, o el bloque central (4 dígitos) del CPA.
    Más de 4 dígitos sueltos (p. ej. 10001 o 8 sin letras) → "Codigo Postal No Valido".
    """
    s = (value or "").strip().upper().replace(" ", "")
    if not s:
        return ""
    m = re.match(r"^([A-Z])?(\d{4})([A-Z]{3})?$", s)
    if m and m.group(2):
        return m.group(2)
    d = "".join(c for c in s if c.isdigit())
    if len(d) < 4:
        return d
    if len(d) > 4:
        return d[:4]
    return d


def _cm_from_db(v) -> int:
    """Medidas en BD ya están en centímetros (enteros para Busplus)."""
    if v is None:
        return 0
    try:
        if isinstance(v, Decimal):
            return int(round(float(v)))
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


@viacargo_shipping_bp.route("/public/viacargo-cotizar", methods=["POST"])
def public_viacargo_cotizar():
    """
    Carga dimensiones y peso desde productos, arma bulto(s) y devuelve solo el TOTAL
    de VIA CARGO PLUS ED (entero, pesos) o error.
    """
    data = request.get_json(silent=True) or {}
    items = data.get("items")
    cp_dst = data.get("codigo_postal_destinatario")
    declared = data.get("importe_valor_declarado")

    if not isinstance(items, list) or not items:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Debe enviar items: lista de { product_id, quantity }",
                }
            ),
            400,
        )
    if not cp_dst or not str(cp_dst).strip():
        return jsonify({"success": False, "error": "codigo_postal_destinatario requerido"}), 400
    try:
        val_decl = int(float(declared)) if declared is not None else 0
    except (TypeError, ValueError):
        return (
            jsonify({"success": False, "error": "importe_valor_declarado inválido"}),
            400,
        )
    if val_decl < 0:
        return jsonify({"success": False, "error": "importe_valor_declarado inválido"}), 400

    id_cliente = os.getenv("BUSPLUS_ID_CLIENTE_REMITENTE", "99999999")
    id_centro = os.getenv("BUSPLUS_ID_CENTRO_REMITENTE", "99")
    cp_remit = _norm_cp_busplus(os.getenv("BUSPLUS_CODIGO_POSTAL_REMITENTE", "5000"))
    busplus_url = os.getenv("BUSPLUS_COTIZAR_URL", "").strip() or None

    cp_dest_n = _norm_cp_busplus(str(cp_dst))
    if len(cp_dest_n) < 4:
        return (
            jsonify(
                {
                    "success": False,
                    "error": MSG_CP_INVALIDO,
                }
            ),
            400,
        )
    if len(cp_remit) < 4:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Configuración de código postal de origen inválida (BUSPLUS_CODIGO_POSTAL_REMITENTE).",
                }
            ),
            500,
        )

    total_qty = 0
    total_kg = 0.0
    max_largo_cm = 0
    max_ancho_cm = 0
    per_line_stacked_h_cm: list = []

    for raw in items:
        if not isinstance(raw, dict):
            continue
        pid = raw.get("product_id")
        try:
            qty = int(raw.get("quantity", 0))
        except (TypeError, ValueError):
            qty = 0
        if qty < 1:
            continue
        try:
            puid = uuid.UUID(str(pid))
        except (ValueError, TypeError):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"product_id inválido: {pid!r}",
                    }
                ),
                400,
            )
        p = Product.query.get(puid)
        if not p:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Producto no encontrado: {pid!r}",
                    }
                ),
                400,
            )
        d_cm = p.viacargo_depth_cm
        w_cm = p.viacargo_width_cm
        h_cm = p.viacargo_height_cm
        kg = p.viacargo_weight_kg
        if d_cm is None or w_cm is None or h_cm is None or kg is None:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Faltan datos de embalaje Vía Cargo del producto {pid}",
                    }
                ),
                400,
            )
        w_kg = float(kg) if not isinstance(kg, Decimal) else float(kg)
        largo_cm = _cm_from_db(d_cm)
        ancho_cm = _cm_from_db(w_cm)
        alto_unit_cm = _cm_from_db(h_cm)
        if w_kg <= 0 or largo_cm <= 0 or ancho_cm <= 0 or alto_unit_cm <= 0:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Medidas o peso Vía Cargo inválidos en producto {pid}",
                    }
                ),
                400,
            )
        line_kg = w_kg * qty
        total_qty += qty
        total_kg += line_kg
        max_largo_cm = max(max_largo_cm, largo_cm)
        max_ancho_cm = max(max_ancho_cm, ancho_cm)
        per_line_stacked_h_cm.append(alto_unit_cm * qty)

    if total_qty < 1:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "No hay items válidos con quantity >= 1",
                }
            ),
            400,
        )

    alto_cm = max(per_line_stacked_h_cm) if per_line_stacked_h_cm else 0

    try:
        payload = build_payload_strings(
            id_cliente=id_cliente,
            id_centro=id_centro,
            cp_remitente=cp_remit,
            cp_destinatario=cp_dest_n,
            importe_valor_declarado=val_decl,
            numero_bultos=total_qty,
            kilos=total_kg,
            largo_cm=max_largo_cm,
            alto_cm=alto_cm,
            ancho_cm=max_ancho_cm,
        )
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    total, err, bus_http = cotizar_busplus_payload(payload, url=busplus_url)
    if err:
        # Busplus usa 4xx p. ej. 404 "Codigo Postal No Valido" (validación), no "Bad Gateway"
        st = 502
        if bus_http is not None and 400 <= bus_http < 500:
            st = 400
        elif bus_http is None:
            st = 502  # error de red
        user_err = _user_facing_cotizar_error(err, bus_http)
        logger.warning("Viacargo cotizar fallo: %s (HTTP %s → %s)", err, bus_http, st)
        return jsonify({"success": False, "error": user_err}), st

    return jsonify({"success": True, "data": {"total": total}})
