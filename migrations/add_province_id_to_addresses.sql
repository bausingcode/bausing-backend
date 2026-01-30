-- Migración: Agregar province_id a addresses
-- Descripción: Agrega el campo province_id a la tabla addresses y crea la foreign key

-- Agregar columna province_id (nullable inicialmente para permitir migración de datos existentes)
ALTER TABLE addresses ADD COLUMN IF NOT EXISTS province_id UUID;

-- Agregar foreign key constraint
ALTER TABLE addresses 
ADD CONSTRAINT fk_addresses_province 
FOREIGN KEY (province_id) REFERENCES provinces(id) ON DELETE RESTRICT;

-- Crear índice para mejorar el rendimiento
CREATE INDEX IF NOT EXISTS idx_addresses_province_id ON addresses(province_id);

-- Nota: La columna province (VARCHAR) se mantiene por compatibilidad temporalmente
-- Se puede eliminar después de migrar todos los datos a province_id
