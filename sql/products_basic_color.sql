-- Color básico opcional (vitrina / filtro catálogo): negro, beige, gris, blanco
ALTER TABLE products ADD COLUMN IF NOT EXISTS basic_color VARCHAR(24) NULL;
