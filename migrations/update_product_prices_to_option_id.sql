-- Migración: Actualizar product_prices para usar product_variant_option_id en lugar de product_variant_id
-- Descripción: Cambia la relación de precios de variantes a opciones de variantes
--              para permitir que cada opción tenga sus propios precios por localidad

-- 1. Agregar la nueva columna product_variant_option_id
ALTER TABLE product_prices 
ADD COLUMN IF NOT EXISTS product_variant_option_id UUID;

-- 2. Migrar los datos existentes (asociar precios a la primera opción de cada variante)
-- Si una variante tiene opciones, asignar los precios a la primera opción
-- Si no tiene opciones, crear una opción "Default" y asignar los precios ahí
DO $$
DECLARE
    price_record RECORD;
    option_id_var UUID;
BEGIN
    -- Para cada precio existente asociado a una variante
    FOR price_record IN 
        SELECT pp.id as price_id, pp.product_variant_id, pp.locality_id, pp.price
        FROM product_prices pp
        WHERE pp.product_variant_option_id IS NULL
          AND pp.product_variant_id IS NOT NULL
    LOOP
        -- Buscar si la variante ya tiene opciones
        SELECT id INTO option_id_var
        FROM product_variant_options
        WHERE product_variant_id = price_record.product_variant_id
        LIMIT 1;
        
        -- Si no hay opciones, crear una opción "Default"
        IF option_id_var IS NULL THEN
            INSERT INTO product_variant_options (id, product_variant_id, name, stock, created_at)
            VALUES (gen_random_uuid(), price_record.product_variant_id, 'Default', 0, CURRENT_TIMESTAMP)
            RETURNING id INTO option_id_var;
        END IF;
        
        -- Actualizar el precio para asociarlo a la opción
        UPDATE product_prices
        SET product_variant_option_id = option_id_var
        WHERE id = price_record.price_id;
    END LOOP;
END $$;

-- 3. Hacer la columna NOT NULL después de migrar los datos
ALTER TABLE product_prices
ALTER COLUMN product_variant_option_id SET NOT NULL;

-- 4. Agregar el foreign key constraint
ALTER TABLE product_prices
ADD CONSTRAINT fk_product_prices_variant_option
FOREIGN KEY (product_variant_option_id) 
REFERENCES product_variant_options(id) 
ON DELETE CASCADE;

-- 5. Eliminar el constraint y columna antigua
ALTER TABLE product_prices
DROP CONSTRAINT IF EXISTS product_prices_product_variant_id_fkey;

ALTER TABLE product_prices
DROP COLUMN IF EXISTS product_variant_id;

-- 6. Crear índice para mejorar el rendimiento
CREATE INDEX IF NOT EXISTS idx_product_prices_variant_option_id 
ON product_prices(product_variant_option_id);

-- 7. Comentarios para documentación
COMMENT ON COLUMN product_prices.product_variant_option_id IS 
'ID de la opción de variante asociada. Los precios ahora están asociados a opciones específicas, permitiendo diferentes precios por localidad para cada opción.';
