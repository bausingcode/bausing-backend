"""
Cálculo de descuentos por cupón en checkout (servidor).
Los montos se aplican solo sobre productos; el envío no se descuenta.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func

from database import db
from models.club_beneficios_item import ClubBeneficiosItem
from models.coupon import Coupon


def normalize_coupon_code(raw: Any) -> str:
    if raw is None:
        return ""
    return str(raw).strip().upper()


def _money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_club_beneficios_product_id_set() -> set:
    rows = db.session.query(ClubBeneficiosItem.product_id).all()
    return {r[0] for r in rows if r[0] is not None}


def load_coupon_for_update(code: str) -> Optional[Coupon]:
    if not code:
        return None
    return (
        Coupon.query.filter(func.lower(Coupon.code) == code.lower())
        .with_for_update()
        .first()
    )


def validate_coupon_row(c: Coupon, now: Optional[datetime] = None) -> Optional[str]:
    """Devuelve mensaje de error o None si es válido."""
    if now is None:
        now = datetime.now(timezone.utc)
    if not c.is_active:
        return "Este cupón no está activo"
    if c.valid_from and c.valid_from > now:
        return "Este cupón aún no es válido"
    if c.valid_until and c.valid_until < now:
        return "Este cupón ha expirado"
    if c.max_uses is not None and int(c.uses_count or 0) >= int(c.max_uses):
        return "Este cupón ya no tiene usos disponibles"
    return None


def _parse_uuid(value: Any) -> Optional[uuid.UUID]:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _find_category_rate(
    line: Dict[str, Any],
    category_discount_rules: List[Dict[str, Any]],
) -> Optional[float]:
    """
    Busca la tasa de descuento (%) que aplica a una línea según sus categorías.
    Subcategoría toma precedencia sobre categoría principal.
    Devuelve None si ninguna regla coincide.
    """
    line_cat_id = str(line.get("category_id") or "").strip()
    line_sub_ids = {str(s).strip() for s in (line.get("subcategory_ids") or []) if s}

    # Primero buscar coincidencia por subcategoría (mayor especificidad)
    for rule in category_discount_rules:
        rule_sub = str(rule.get("subcategory_id") or "").strip()
        if rule_sub and rule_sub in line_sub_ids:
            return float(rule["discount_value"])

    # Luego buscar coincidencia por categoría principal
    for rule in category_discount_rules:
        rule_cat = str(rule.get("category_id") or "").strip()
        rule_sub = str(rule.get("subcategory_id") or "").strip()
        if rule_cat and not rule_sub and rule_cat == line_cat_id:
            return float(rule["discount_value"])

    return None


def compute_coupon_discount_amount(
    coupon: Coupon,
    order_lines: List[Dict[str, Any]],
    club_ids: set,
    category_discount_rules: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[float, List[float], Optional[str]]:
    """
    order_lines: lista de dicts con:
      - 'product_id' (uuid)
      - 'precio_total_original' (float)
      - 'category_id' (str uuid, opcional — para reglas por categoría)
      - 'subcategory_ids' (list de str uuid, opcional)

    category_discount_rules: lista de dicts con 'category_id', 'subcategory_id', 'discount_value'.
      Solo aplica cuando coupon.club_beneficios_only=True y discount_type='percentage'.

    Devuelve (total_descuento, descuentos_por_linea_misma_orden, error).
    """
    n = len(order_lines)
    if n == 0:
        return 0.0, [], "El carrito no tiene ítems válidos"

    eligible = [0.0] * n
    coupon_product_id = _parse_uuid(coupon.product_id)

    if coupon_product_id is not None:
        # Cupón específico para un producto: solo aplica a líneas con ese product_id
        for i, line in enumerate(order_lines):
            pid = _parse_uuid(line.get("product_id"))
            if pid == coupon_product_id:
                eligible[i] = float(line["precio_total_original"])
    elif coupon.club_beneficios_only:
        for i, line in enumerate(order_lines):
            pid = _parse_uuid(line.get("product_id"))
            if pid in club_ids:
                eligible[i] = float(line["precio_total_original"])
    else:
        for i, line in enumerate(order_lines):
            eligible[i] = float(line["precio_total_original"])

    eligible_sum = sum(eligible)
    if coupon_product_id is not None and eligible_sum <= 0:
        return (
            0.0,
            [],
            "Este cupón solo aplica a un producto específico que no está en el carrito",
        )
    if coupon.club_beneficios_only and eligible_sum <= 0:
        return (
            0.0,
            [],
            "Este cupón solo aplica a productos de Club Beneficios y no hay ninguno en el carrito",
        )

    # Descuentos por categoría: aplica solo para cupones club + percentage con reglas configuradas
    has_cat_rules = (
        bool(category_discount_rules)
        and coupon.club_beneficios_only
        and str(coupon.discount_type).lower() == "percentage"
    )

    if has_cat_rules:
        total_discount = Decimal("0")
        discounts = [0.0] * n

        for i, line in enumerate(order_lines):
            if eligible[i] <= 0:
                continue
            rate = _find_category_rate(line, category_discount_rules)  # type: ignore[arg-type]
            if rate is None:
                # Sin regla específica → usar descuento predeterminado del cupón
                rate = float(coupon.discount_value)
            line_raw = Decimal(str(eligible[i])) * Decimal(str(rate)) / Decimal("100")
            line_discount = float(line_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            discounts[i] = line_discount
            total_discount += Decimal(str(line_discount))

        return float(total_discount), discounts, None

    # Lógica original (sin reglas por categoría)
    dv = float(coupon.discount_value)
    if coupon.discount_type == "percentage":
        raw = eligible_sum * (dv / 100.0)
    else:
        raw = min(dv, eligible_sum)

    total_discount = float(_money(raw))
    if total_discount <= 0:
        return 0.0, [0.0] * n, None

    # Repartir proporcionalmente en líneas elegibles
    discounts = [0.0] * n
    if eligible_sum > 0:
        allocated = 0.0
        for i in range(n):
            if eligible[i] <= 0:
                continue
            share = total_discount * (eligible[i] / eligible_sum)
            discounts[i] = float(_money(share))
            allocated += discounts[i]
        diff = round(total_discount - allocated, 2)
        if abs(diff) >= 0.01 and n > 0:
            # Ajustar centavos en la última línea elegible
            for j in range(n - 1, -1, -1):
                if eligible[j] > 0:
                    discounts[j] = round(discounts[j] + diff, 2)
                    break
    return total_discount, discounts, None
