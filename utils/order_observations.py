"""Texto de observaciones para órdenes / CRM a partir del payload del checkout."""

from __future__ import annotations

from typing import Any, Mapping

_METHOD_LABELS = {
    "wallet": "Billetera Bausing",
    "cash": "Efectivo",
    "transfer": "Transferencia",
    "card": "Tarjeta",
}


def _format_amount(amount: float) -> str:
    try:
        value = float(amount)
    except (TypeError, ValueError):
        value = 0.0
    return f"${value:,.0f}".replace(",", ".")


def _card_detail_suffix(card_payment_details: Any) -> str:
    """" (Visa Crédito, Banco Galicia, 3 cuotas)" a partir de card_payment_details, o ''."""
    if not isinstance(card_payment_details, Mapping):
        return ""

    parts: list[str] = []
    card_label = str(
        card_payment_details.get("card_type_name")
        or card_payment_details.get("card_type_code")
        or ""
    ).strip()
    if card_label:
        parts.append(card_label)

    bank = str(card_payment_details.get("bank_name") or "").strip()
    if bank:
        parts.append(bank)

    installments = card_payment_details.get("installments")
    if installments is not None:
        try:
            n = int(installments)
            if n > 1:
                parts.append(f"{n} cuotas")
        except (TypeError, ValueError):
            pass

    return f" ({', '.join(parts)})" if parts else ""


def _payment_breakdown_text(data: Mapping[str, Any]) -> str:
    """
    Detalle de cada medio de pago usado y su monto, distinguiendo lo ya
    cobrado ("Pagado con...") de lo pendiente de cobro al recibir
    ("A pagar con..."), a partir de `payment_methods` (lo manda el checkout
    con un item por medio, incluso en pagos combinados).

    Ej.: "Pagado con Billetera Bausing: $5.000 | A pagar con Efectivo: $30.000 |
    A pagar con Tarjeta: $50.000 (Visa Crédito, Banco Galicia, 3 cuotas)"
    """
    methods = data.get("payment_methods")
    if not isinstance(methods, list) or not methods:
        return ""

    card_payment_details = data.get("card_payment_details")

    lines: list[str] = []
    for pm in methods:
        if not isinstance(pm, Mapping):
            continue
        try:
            amount = float(pm.get("amount", 0))
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            continue

        method = str(pm.get("method") or "").strip().lower()
        label = _METHOD_LABELS.get(method, method.capitalize() or "Pago")
        suffix = _card_detail_suffix(card_payment_details) if method == "card" else ""
        prefix = "Pagado con" if pm.get("processed") else "A pagar con"
        lines.append(f"{prefix} {label}: {_format_amount(amount)}{suffix}")

    return " | ".join(lines)


def resolve_order_observations(data: Mapping[str, Any], *, max_len: int = 2000) -> str:
    """
    Combina la nota libre del checkout (`observations`) con el detalle de los
    medios de pago usados y sus montos (`payment_methods`), para que en el
    CRM siempre quede registrado cuánto se pagó con cada medio —billetera,
    efectivo, tarjeta, transferencia— incluso cuando el pago está combinado
    entre varios.
    """
    custom_note = str(data.get("observations") or "").strip()
    breakdown = _payment_breakdown_text(data)

    if custom_note and breakdown:
        text = f"{custom_note} | {breakdown}"
    elif breakdown:
        text = breakdown
    elif custom_note:
        text = custom_note
    else:
        # Backward compat: sin payment_methods[], al menos mencionar la tarjeta si la hay.
        suffix = _card_detail_suffix(data.get("card_payment_details"))
        text = f"Pago con tarjeta{suffix}" if suffix else ""

    return text[:max_len]
