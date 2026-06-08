-- Soporte para cupones específicos por producto.
-- product_id NULL = aplica a todo el catálogo; UUID = solo al producto indicado.
ALTER TABLE coupons ADD COLUMN IF NOT EXISTS product_id UUID NULL REFERENCES products(id) ON DELETE SET NULL;
