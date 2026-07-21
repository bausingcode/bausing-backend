-- Envío acordado por catálogo (excepto "Pais") para pedidos cuyo carrito
-- contiene únicamente productos de la categoría Almohadas y accesorios.

ALTER TABLE catalogs
  ADD COLUMN IF NOT EXISTS accessories_shipping_price NUMERIC(10, 2);
