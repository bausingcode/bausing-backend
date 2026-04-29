-- Características opcionales por tipo de electrodoméstico (admin + PDP)
ALTER TABLE products
  ADD COLUMN IF NOT EXISTS smart_screen_size VARCHAR(128),
  ADD COLUMN IF NOT EXISTS smart_resolution VARCHAR(128),
  ADD COLUMN IF NOT EXISTS smart_tv BOOLEAN,
  ADD COLUMN IF NOT EXISTS ac_inverter BOOLEAN,
  ADD COLUMN IF NOT EXISTS ac_climate_type VARCHAR(255),
  ADD COLUMN IF NOT EXISTS ac_frigorias INTEGER,
  ADD COLUMN IF NOT EXISTS wm_load_type VARCHAR(64),
  ADD COLUMN IF NOT EXISTS wm_wash_capacity_kg NUMERIC(10, 2),
  ADD COLUMN IF NOT EXISTS fridge_capacity_liters NUMERIC(10, 2),
  ADD COLUMN IF NOT EXISTS freezer_capacity_liters NUMERIC(10, 2);
