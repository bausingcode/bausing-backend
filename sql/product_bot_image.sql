-- Imagen "para bot" (uso interno, nunca se muestra en la vitrina). Por defecto es la primera
-- imagen del producto (calculada al leer); si se carga una propia queda fija en su formato
-- original, sin recompresión.
ALTER TABLE products ADD COLUMN IF NOT EXISTS bot_image_url TEXT NULL;
ALTER TABLE products ADD COLUMN IF NOT EXISTS bot_image_is_custom BOOLEAN NOT NULL DEFAULT FALSE;
