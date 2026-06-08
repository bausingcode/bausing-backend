-- Descuentos por categoría/subcategoría para cupones Club Beneficios
-- Permite configurar porcentajes de descuento distintos por categoría o subcategoría.
-- La subcategoría toma precedencia sobre la categoría cuando ambas coinciden.

CREATE TABLE IF NOT EXISTS coupon_category_discounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coupon_id UUID NOT NULL REFERENCES coupons(id) ON DELETE CASCADE,
    category_id UUID,
    subcategory_id UUID,
    discount_value NUMERIC(12, 2) NOT NULL
        CHECK (discount_value > 0 AND discount_value <= 100)
);

CREATE INDEX IF NOT EXISTS idx_coupon_category_discounts_coupon_id
    ON coupon_category_discounts(coupon_id);
