-- Migración: Agregar columnas faltantes a catalogs
-- Descripción: Asegura que la tabla catalogs tenga las columnas description y updated_at para compatibilidad con el modelo

-- Agregar columna description si no existe
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'catalogs' 
        AND column_name = 'description'
    ) THEN
        ALTER TABLE catalogs 
        ADD COLUMN description TEXT;
    END IF;
END $$;

-- Agregar columna updated_at si no existe
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'catalogs' 
        AND column_name = 'updated_at'
    ) THEN
        ALTER TABLE catalogs 
        ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        
        -- Actualizar updated_at con el valor de created_at para registros existentes
        UPDATE catalogs 
        SET updated_at = created_at 
        WHERE updated_at IS NULL;
        
        -- Hacer updated_at NOT NULL después de actualizar
        ALTER TABLE catalogs 
        ALTER COLUMN updated_at SET NOT NULL;
    END IF;
END $$;
