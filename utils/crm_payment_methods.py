"""IDs de medios de pago del CRM (formaPagos.medios_pago_id)."""

from __future__ import annotations

# 1 = efectivo / abonar al recibir, 2 = transferencia, 3 = billetera, 4 = tarjeta
CRM_MEDIOS_PAGO_EFECTIVO = 1
CRM_MEDIOS_PAGO_TRANSFERENCIA = 2
CRM_MEDIOS_PAGO_BILLETERA = 61
CRM_MEDIOS_PAGO_TARJETA = 62


def crm_medios_pago_id_for_checkout_method(method: str) -> int:
    """Mapea el método del checkout web al medios_pago_id del CRM."""
    m = (method or "").strip().lower()
    if m == "wallet":
        return CRM_MEDIOS_PAGO_BILLETERA
    if m == "card":
        return CRM_MEDIOS_PAGO_TARJETA
    if m == "transfer":
        return CRM_MEDIOS_PAGO_TRANSFERENCIA
    return CRM_MEDIOS_PAGO_EFECTIVO
