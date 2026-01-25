-- Migración: Migrar product_prices de locality_id a catalog_id
-- Descripción: Cambia la estructura de precios para usar catálogos en lugar de localidades individuales
-- IMPORTANTE: Ejecutar después de crear los catálogos y las relaciones locality_catalogs

-- 1. Agregar columna catalog_id a product_prices
ALTER TABLE product_prices 
ADD COLUMN IF NOT EXISTS catalog_id UUID;

-- 2. Migrar los datos existentes: asignar catalog_id basado en locality_id
-- Si una localidad pertenece a múltiples catálogos, se creará un precio para cada catálogo
DO $$
DECLARE
    price_record RECORD;
    catalog_id_var UUID;
BEGIN
    -- Para cada precio existente
    FOR price_record IN 
        SELECT pp.id as price_id, pp.locality_id, pp.product_variant_id, pp.price
        FROM product_prices pp
        WHERE pp.catalog_id IS NULL
    LOOP
        -- Obtener el primer catálogo asociado a esta localidad
        -- Si hay múltiples, se creará un precio para cada uno
        FOR catalog_id_var IN
            SELECT lc.catalog_id
            FROM locality_catalogs lc
            WHERE lc.locality_id = price_record.locality_id
        LOOP
            -- Crear un nuevo precio para este catálogo
            INSERT INTO product_prices (id, product_variant_id, catalog_id, price, locality_id)
            VALUES (
                gen_random_uuid(),
                price_record.product_variant_id,
                catalog_id_var,
                price_record.price,
                price_record.locality_id  -- Mantener locality_id por ahora para referencia
            )
            ON CONFLICT DO NOTHING;
        END LOOP;
        
        -- Si la localidad no tiene catálogo asignado, mantener el precio original
        -- pero marcar catalog_id como NULL (se deberá asignar manualmente)
    END LOOP;
END $$;

-- 3. Opcional: Eliminar precios duplicados si es necesario
-- (Comentar si quieres mantener ambos sistemas temporalmente)

-- 4. Hacer catalog_id NOT NULL después de verificar que todos los precios tienen catálogo
-- ALTER TABLE product_prices
-- ALTER COLUMN catalog_id SET NOT NULL;

-- 5. Agregar foreign key constraint (solo si no existe)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'product_prices_catalog_id_fkey'
    ) THEN
        ALTER TABLE product_prices
        ADD CONSTRAINT product_prices_catalog_id_fkey 
        FOREIGN KEY (catalog_id) REFERENCES catalogs(id) ON DELETE CASCADE;
    END IF;
END $$;

-- 6. Crear índice para mejorar el rendimiento
CREATE INDEX IF NOT EXISTS idx_product_prices_catalog_id ON product_prices(catalog_id);

-- Nota: Después de verificar que todo funciona correctamente, puedes:
-- 1. Eliminar la columna locality_id de product_prices (si ya no se necesita)
-- 2. Hacer catalog_id NOT NULL
-- 3. Eliminar los precios duplicados que mantienen locality_id
