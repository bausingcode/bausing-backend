-- Migración: Agregar campos de transporte tercerizado a crm_zone_localities
-- Fecha: 2025-01-XX
-- Descripción: Agrega campos para marcar localidades con transporte tercerizado y su precio de envío

-- Agregar columna is_third_party_transport
ALTER TABLE crm_zone_localities
ADD COLUMN IF NOT EXISTS is_third_party_transport BOOLEAN NOT NULL DEFAULT FALSE;

-- Agregar columna shipping_price
ALTER TABLE crm_zone_localities
ADD COLUMN IF NOT EXISTS shipping_price NUMERIC(10, 2) NULL;

-- Agregar columna updated_at si no existe
ALTER TABLE crm_zone_localities
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- Crear función para actualizar updated_at automáticamente (si no existe)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Crear trigger para actualizar updated_at automáticamente (si no existe)
DROP TRIGGER IF EXISTS update_crm_zone_localities_updated_at ON crm_zone_localities;
CREATE TRIGGER update_crm_zone_localities_updated_at
    BEFORE UPDATE ON crm_zone_localities
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Comentarios para documentación
COMMENT ON COLUMN crm_zone_localities.is_third_party_transport IS 'Indica si esta localidad usa transporte tercerizado';
COMMENT ON COLUMN crm_zone_localities.shipping_price IS 'Precio de envío configurado para transporte tercerizado (en pesos)';
COMMENT ON COLUMN crm_zone_localities.updated_at IS 'Fecha y hora de última actualización del registro';
