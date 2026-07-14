-- Agrega días estimados de entrega por catálogo, y el catálogo resuelto para
-- cada orden (según la localidad de entrega), para poder mostrarlo en:
--   - el email de confirmación de compra
--   - la pantalla "compra realizada"
--   - el seguimiento de pedido

ALTER TABLE catalogs
  ADD COLUMN IF NOT EXISTS estimated_delivery_days_min INTEGER,
  ADD COLUMN IF NOT EXISTS estimated_delivery_days_max INTEGER;

ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS catalog_id UUID REFERENCES catalogs(id) ON DELETE SET NULL;
