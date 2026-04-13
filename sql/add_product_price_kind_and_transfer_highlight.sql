-- Precios: efectivo/transferencia (transfer) vs tarjeta (card). Legacy sin columna = transfer.
ALTER TABLE product_prices
  ADD COLUMN IF NOT EXISTS price_kind VARCHAR(20) NOT NULL DEFAULT 'transfer';

UPDATE product_prices SET price_kind = 'transfer' WHERE price_kind IS NULL OR price_kind = '';

-- Evitar duplicar mismo catálogo + tipo para la misma opción
CREATE UNIQUE INDEX IF NOT EXISTS uq_product_prices_option_catalog_kind
  ON product_prices (product_variant_id, catalog_id, price_kind)
  WHERE catalog_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_product_prices_option_locality_kind
  ON product_prices (product_variant_id, locality_id, price_kind)
  WHERE locality_id IS NOT NULL AND catalog_id IS NULL;

-- Mostrar en tienda precio transferencia tachando lista tarjeta (si no hay promo que lo reemplace en UI)
ALTER TABLE products
  ADD COLUMN IF NOT EXISTS show_transfer_price_highlight BOOLEAN NOT NULL DEFAULT false;
