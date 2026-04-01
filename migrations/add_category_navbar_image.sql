-- Imagen opcional para el panel del mega menú (navbar) por categoría principal
ALTER TABLE categories ADD COLUMN IF NOT EXISTS navbar_image_url TEXT;
