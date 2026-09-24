-- Slug legible para la URL pública del producto (ej: colchon-queen-inducol).
-- La URL con el ID actual sigue funcionando: el slug es un campo adicional, no reemplaza al ID.
ALTER TABLE products ADD COLUMN IF NOT EXISTS slug VARCHAR(300) NULL;

-- Único solo entre valores no nulos (permite productos viejos sin slug hasta que se backfillee).
CREATE UNIQUE INDEX IF NOT EXISTS products_slug_unique_idx ON products (slug) WHERE slug IS NOT NULL;
