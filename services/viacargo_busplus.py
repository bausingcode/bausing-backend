# -*- coding: utf-8 -*-
"""
Integración con el endpoint de cotización Busplus (Vía Cargo).
"""
import json
import logging
from typing import Any, Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

BUSPLUS_COTIZAR_URL = "https://ws.busplus.com.ar/alerce/cotizar"
VIA_CARGO_PLUS_ED_LABEL = "VIA CARGO PLUS ED"
REQUEST_TIMEOUT_S = 30


def _fmt_dim_m(value: float) -> str:
    if value < 0:
        value = 0.0
    s = f"{value:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def extract_viacargo_plus_ed_total(response_json: Any) -> Tuple[int, Optional[str]]:
    """
    Devuelve (total_int, error_message).
    Si OK: (total, None)
    """
    if not isinstance(response_json, dict):
        return 0, "La respuesta no es un objeto JSON válido"
    ctz = response_json.get("Cotizacion")
    if ctz is None:
        ctz = response_json.get("cotizacion")
    if not isinstance(ctz, list):
        return 0, "La respuesta no contiene la propiedad Cotizacion o no es un array"
    for row in ctz:
        if not isinstance(row, dict):
            continue
        desc = row.get("PRODUCTO_DESCRIPCION")
        if desc is None:
            desc = row.get("Producto_Descripcion")
        if desc is None:
            desc = row.get("producto_descripcion")
        if not isinstance(desc, str):
            continue
        if desc.strip() == VIA_CARGO_PLUS_ED_LABEL:
            total_raw = row.get("TOTAL", row.get("Total", row.get("total")))
            n = _to_float(total_raw)
            if n is None:
                return 0, "En la cotización, TOTAL no es un número válido"
            return int(round(n)), None
    return 0, f'No se encontró el producto "{VIA_CARGO_PLUS_ED_LABEL}" en la cotización'


def cotizar_busplus_payload(
    payload: dict,
    url: Optional[str] = None,
) -> Tuple[Optional[int], Optional[str], Optional[int]]:
    """
    POST al endpoint; devuelve (total, error, status_http_busplus o None si no hubo respuesta).
    """
    raw_url = (url or BUSPLUS_COTIZAR_URL or "").strip()
    post_url = raw_url.rstrip("/")

    try:
        r = requests.post(
            post_url,
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT_S,
        )
    except requests.RequestException as e:
        logger.warning("Viacargo cotizar: error de red: %s", e)
        return None, f"Error al conectar con el servicio de cotización: {e!s}", None

    http_status = r.status_code

    try:
        data = r.json()
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Viacargo cotizar: JSON inválido: %s", e)
        return None, "La respuesta del servicio de cotización no es JSON válido", http_status

    if not r.ok:
        err = f"El servicio de cotización respondió con estado {r.status_code}"
        if isinstance(data, dict):
            bus_msg = data.get("message") or data.get("Message")
            if isinstance(bus_msg, str) and bus_msg.strip():
                err = f"{err}: {bus_msg.strip()}"
        logger.warning("Viacargo cotizar: %s", err)
        return None, err, http_status

    total, err = extract_viacargo_plus_ed_total(data)
    if err:
        return None, err, http_status
    if total < 0:
        return None, "TOTAL de cotización inválido", http_status
    return total, None, http_status


def build_payload_strings(
    id_cliente: str,
    id_centro: str,
    cp_remitente: str,
    cp_destinatario: str,
    importe_valor_declarado: int,
    numero_bultos: int,
    kilos: float,
    largo_m: float,
    alto_m: float,
    ancho_m: float,
    tipo_portes: str = "P",
) -> Dict[str, Any]:
    """
    JSON para Alerce/Busplus. Id, CP, bultos e importe como números en JSON.
    """
    cp_r = str(cp_remitente).strip()[:4]
    cp_d = str(cp_destinatario).strip()[:4]
    if not (len(cp_r) == 4 and cp_r.isdigit() and len(cp_d) == 4 and cp_d.isdigit()):
        raise ValueError("Códigos postales deben ser 4 dígitos (ya normalizados al llamar)")

    def _id_int(label: str, v: str) -> int:
        s = str(v).strip()
        if not s.isdigit():
            raise ValueError(f"{label} debe ser numérico, recibido: {v!r}")
        return int(s)

    return {
        "IdClienteRemitente": _id_int("IdClienteRemitente", id_cliente),
        "IdCentroRemitente": _id_int("IdCentroRemitente", id_centro),
        "CodigoPostalRemitente": int(cp_r),
        "CodigoPostalDestinatario": int(cp_d),
        "ImporteValorDeclarado": int(max(0, importe_valor_declarado)),
        "NumeroBultos": max(1, int(numero_bultos)),
        "Kilos": _fmt_dim_m(kilos),
        "Largo": _fmt_dim_m(largo_m),
        "Alto": _fmt_dim_m(alto_m),
        "Ancho": _fmt_dim_m(ancho_m),
        "TipoPortes": (tipo_portes or "P").strip() or "P",
    }
