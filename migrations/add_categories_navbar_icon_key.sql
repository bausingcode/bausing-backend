-- Icono del mega menú para categorías / subcategorías (clave resuelta en el frontend).
ALTER TABLE categories ADD COLUMN IF NOT EXISTS navbar_icon_key VARCHAR(64) NULL;
