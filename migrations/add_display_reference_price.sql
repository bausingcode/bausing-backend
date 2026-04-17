-- Precio de referencia solo para vitrina (tachado / marketing). No afecta totales ni checkout.
ALTER TABLE products ADD COLUMN IF NOT EXISTS display_reference_price NUMERIC(12, 2) NULL;
