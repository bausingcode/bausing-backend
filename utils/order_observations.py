"""Texto de observaciones para órdenes / CRM a partir del payload del checkout."""

from __future__ import annotations

from typing import Any, Mapping


def resolve_order_observations(data: Mapping[str, Any], *, max_len: int = 2000) -> str:
    """
    Prioriza `observations` del front; si no viene, arma el texto desde
    `card_payment_details` (tarjeta, banco, cuotas).
    """
    raw = data.get("observations")
    if raw is not None:
        text = str(raw).strip()
        if text:
            return text[:max_len]

    cpd = data.get("card_payment_details")
    if not isinstance(cpd, dict):
        return ""

    parts: list[str] = []
    card_label = (cpd.get("card_type_name") or cpd.get("card_type_code") or "").strip()
    if card_label:
        parts.append(f"Tarjeta: {card_label}")
    bank = (cpd.get("bank_name") or "").strip()
    if bank:
        parts.append(f"Banco: {bank}")
    installments = cpd.get("installments")
    if installments is not None:
        try:
            n = int(installments)
            if n > 0:
                cuota_word = "cuota" if n == 1 else "cuotas"
                parts.append(f"{n} {cuota_word}")
        except (TypeError, ValueError):
            pass

    if not parts:
        return ""
    return f"Pago con tarjeta: {' | '.join(parts)}"[:max_len]
