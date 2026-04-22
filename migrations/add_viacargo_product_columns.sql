-- Dimensiones y peso para envíos / integración con Viacargo (admin).
ALTER TABLE products ADD COLUMN IF NOT EXISTS viacargo_height_cm NUMERIC(10, 2) NULL;
ALTER TABLE products ADD COLUMN IF NOT EXISTS viacargo_width_cm NUMERIC(10, 2) NULL;
ALTER TABLE products ADD COLUMN IF NOT EXISTS viacargo_depth_cm NUMERIC(10, 2) NULL;
ALTER TABLE products ADD COLUMN IF NOT EXISTS viacargo_weight_kg NUMERIC(10, 2) NULL;
