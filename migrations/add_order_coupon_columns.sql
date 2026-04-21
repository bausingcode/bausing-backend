-- Cupón aplicado en la orden (registro y detalle para el cliente)
ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS coupon_id UUID NULL REFERENCES coupons(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS coupon_code VARCHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS coupon_discount_amount NUMERIC(12, 2) NULL;

COMMENT ON COLUMN orders.coupon_id IS 'Cupón usado en el checkout (FK opcional)';
COMMENT ON COLUMN orders.coupon_code IS 'Código del cupón al momento de la compra';
COMMENT ON COLUMN orders.coupon_discount_amount IS 'Monto descontado (solo productos, sin envío)';
