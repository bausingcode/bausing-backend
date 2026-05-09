-- Colores de vitrina cargados manualmente en admin (JSON array string).
ALTER TABLE products ADD COLUMN IF NOT EXISTS manual_color_labels TEXT NULL;
