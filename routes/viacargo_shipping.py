# -*- coding: utf-8 -*-
import json
import os
import re
import uuid
import logging
from decimal import Decimal

from flask import Blueprint, jsonify, request

from models.product import Product
from models.province import Province
from services.viacargo_busplus import build_payload_strings, cotizar_busplus_payload
from database import db
from models.category import Category, CategoryOption
from models.settings import SystemSettings
from routes.admin import admin_required
from services.viacargo_tarifa import (
    SETTINGS_KEY,
    TIPO_LABELS,
    VIACARGO_TARIFAS,
    ZONA_LABELS,
    ZONAS,
    precios_producto,
    provincias_por_zona,
    tarifas_vigentes,
    zona_viacargo,
)

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
    Productos con tarifa (tipos fijos por subcategoría o tarifas extra por categoría desde el admin): precio fijo por unidad según medida y zona
    (provincia de province_id). El resto: carga dimensiones y peso, arma bulto(s) y
    cotiza VIA CARGO PLUS ED en Busplus. Devuelve el TOTAL (pesos) o error.
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

    provincia_nombre = None
    province_id = data.get("province_id")
    if province_id:
        try:
            prov = Province.query.get(uuid.UUID(str(province_id)))
        except (ValueError, TypeError):
            prov = None
        provincia_nombre = prov.name if prov else None

    total_qty = 0
    total_kg = 0.0
    max_largo_cm = 0
    max_ancho_cm = 0
    per_line_stacked_h_cm: list = []
    extra_total = 0.0
    tarifa_total = 0
    zona = None
    tarifas = tarifas_vigentes()

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
        if p.viacargo_extra_price is not None:
            extra_total += float(p.viacargo_extra_price) * qty

        # Tarifa fija por tipo/categoría y zona (cada unidad paga su envío)
        fila_precios = precios_producto(p, tarifas)
        if fila_precios:
            if zona is None:
                zona = zona_viacargo(provincia_nombre, cp_dest_n)
                if zona is None:
                    return jsonify({"success": False, "error": MSG_CP_NO_DISPONIBLE_ENVIO}), 400
            precio = fila_precios[ZONAS.index(zona)]
            if precio is not None:
                tarifa_total += int(precio) * qty
                continue
            # Precio vacío para esa zona: se cotiza en Busplus

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
        if zona is None:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "No hay items válidos con quantity >= 1",
                    }
                ),
                400,
            )
        # Todo el carrito con tarifa fija: no hace falta cotizar en Busplus
        return jsonify(
            {
                "success": True,
                "data": {
                    "total": tarifa_total + extra_total,
                    "tarifa_zona": zona,
                },
            }
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

    total, err, bus_http, busplus_response = cotizar_busplus_payload(payload, url=busplus_url)
    if err:
        # Busplus usa 4xx p. ej. 404 "Codigo Postal No Valido" (validación), no "Bad Gateway"
        st = 502
        if bus_http is not None and 400 <= bus_http < 500:
            st = 400
        elif bus_http is None:
            st = 502  # error de red
        user_err = _user_facing_cotizar_error(err, bus_http)
        logger.warning("Viacargo cotizar fallo: %s (HTTP %s → %s)", err, bus_http, st)
        return jsonify({"success": False, "error": user_err, "busplus_payload": payload}), st

    return jsonify(
        {
            "success": True,
            "data": {
                "total": total + tarifa_total + extra_total,
                "tarifa_zona": zona,
                "busplus_payload": payload,
                "busplus_response": busplus_response,
            },
        }
    )


def _tarifas_payload():
    setting = SystemSettings.query.filter_by(key=SETTINGS_KEY).first()
    provincias = provincias_por_zona()
    tarifas = tarifas_vigentes()
    return {
        "zonas": [{"key": z, "label": ZONA_LABELS[z], "provincias": provincias[z]} for z in ZONAS],
        "tipos": [{"key": t, "label": TIPO_LABELS[t]} for t in VIACARGO_TARIFAS],
        "precios": {t: list(p) for t, p in tarifas["precios"].items()},
        "extras": tarifas["extras"],
        "updated_at": setting.updated_at.isoformat() if setting and setting.updated_at else None,
    }


def _precios_validos(fila, nombre: str):
    """Un precio entero > 0 o None (vacío → Busplus) por zona, o mensaje de error."""
    if not isinstance(fila, list) or len(fila) != len(ZONAS):
        return None, f"Faltan precios para {nombre}"
    valores = []
    for v in fila:
        if v is None or v == "":
            valores.append(None)
            continue
        try:
            n = int(round(float(v)))
        except (TypeError, ValueError):
            return None, f"Precio inválido en {nombre}"
        if n <= 0:
            return None, f"Los precios deben ser mayores a 0 ({nombre})"
        valores.append(n)
    return valores, None


@viacargo_shipping_bp.route("/admin/viacargo-tarifas", methods=["GET"])
@admin_required
def admin_get_viacargo_tarifas():
    return jsonify({"success": True, "data": _tarifas_payload()})


@viacargo_shipping_bp.route("/admin/viacargo-tarifas", methods=["PUT"])
@admin_required
def admin_update_viacargo_tarifas():
    """
    Body: { precios: { <tipo>: [precio por zona] },
            extras: [{ id?, label, category_id?, category_option_id?, product_ids?, precios: [precio por zona] }] }
    Cada tarifa extra necesita una categoría o al menos un producto.
    """
    data = request.get_json(silent=True) or {}
    precios = data.get("precios")
    extras = data.get("extras") or []
    if not isinstance(precios, dict) or not isinstance(extras, list):
        return jsonify({"success": False, "error": "precios requerido"}), 400

    limpio = {}
    for tipo in VIACARGO_TARIFAS:
        valores, err = _precios_validos(precios.get(tipo), TIPO_LABELS[tipo])
        if err:
            return jsonify({"success": False, "error": err}), 400
        limpio[tipo] = valores

    extras_limpias = []
    for e in extras:
        if not isinstance(e, dict):
            continue
        label = (e.get("label") or "").strip()
        if not label:
            return jsonify({"success": False, "error": "Cada tarifa agregada necesita un nombre"}), 400
        cat = None
        if e.get("category_id"):
            try:
                cat = Category.query.get(uuid.UUID(str(e.get("category_id"))))
            except (ValueError, TypeError):
                cat = None
            if not cat:
                return jsonify({"success": False, "error": f"Categoría inválida para \"{label}\""}), 400
        try:
            product_ids = list(dict.fromkeys(str(uuid.UUID(str(pid))) for pid in (e.get("product_ids") or [])))
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": f"Producto inválido en \"{label}\""}), 400
        if product_ids:
            encontrados = Product.query.filter(Product.id.in_(product_ids)).count()
            if encontrados != len(product_ids):
                return jsonify({"success": False, "error": f"Algún producto de \"{label}\" ya no existe"}), 400
        if not cat and not product_ids:
            return jsonify({"success": False, "error": f"Elegí una categoría o productos para \"{label}\""}), 400
        opt_id = (e.get("category_option_id") or None) if cat else None
        if opt_id:
            try:
                opt = CategoryOption.query.get(uuid.UUID(str(opt_id)))
            except (ValueError, TypeError):
                opt = None
            if not opt or opt.category_id != cat.id:
                return jsonify({"success": False, "error": f"Opción inválida para \"{label}\""}), 400
        valores, err = _precios_validos(e.get("precios"), label)
        if err:
            return jsonify({"success": False, "error": err}), 400
        extras_limpias.append(
            {
                "id": str(e.get("id") or uuid.uuid4()),
                "label": label,
                "category_id": str(cat.id) if cat else None,
                "category_option_id": str(opt_id) if opt_id else None,
                "product_ids": product_ids,
                "precios": valores,
            }
        )

    try:
        SystemSettings.set_value(
            key=SETTINGS_KEY,
            value=json.dumps({"precios": limpio, "extras": extras_limpias}),
            value_type="json",
            category="shipping",
            description="Tarifa fija Vía Cargo por tipo de producto y zona",
            updated_by=request.admin_user.id,
        )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.exception("Error guardando tarifas Vía Cargo")
        return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({"success": True, "data": _tarifas_payload()})
