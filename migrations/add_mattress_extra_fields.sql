-- Campos adicionales de colchón: altura, tipo de tela, doble pillow, respiradores, agarraderas laterales
-- Ejecutar una vez contra la base del ecommerce (tabla products).

ALTER TABLE products ADD COLUMN IF NOT EXISTS mattress_height_cm INTEGER;
ALTER TABLE products ADD COLUMN IF NOT EXISTS mattress_fabric_type VARCHAR(255);
ALTER TABLE products ADD COLUMN IF NOT EXISTS has_double_pillow BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE products ADD COLUMN IF NOT EXISTS has_moisture_breathers BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE products ADD COLUMN IF NOT EXISTS has_side_handles BOOLEAN NOT NULL DEFAULT FALSE;
