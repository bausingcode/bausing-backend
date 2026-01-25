-- Migración: Actualizar foreign key de product_prices para apuntar a product_variant_options
-- Descripción: Cambia el foreign key de product_prices.product_variant_id 
--              para que apunte a product_variant_options.id en lugar de product_variants.id
--              Esto permite que cada opción de variante tenga sus propios precios por localidad

-- 1. Eliminar el constraint de foreign key existente
ALTER TABLE product_prices
DROP CONSTRAINT IF EXISTS product_prices_product_variant_id_fkey;

-- 2. Migrar los datos existentes (asociar precios a la primera opción de cada variante)
-- Si una variante tiene opciones, asignar los precios a la primera opción
-- Si no tiene opciones, crear una opción "Default" y asignar los precios ahí
DO $$
DECLARE
    price_record RECORD;
    option_id_var UUID;
    variant_id_var UUID;
BEGIN
    -- Para cada precio existente asociado a una variante
    FOR price_record IN 
        SELECT pp.id as price_id, pp.product_variant_id, pp.locality_id, pp.price
        FROM product_prices pp
        WHERE pp.product_variant_id IS NOT NULL
    LOOP
        variant_id_var := price_record.product_variant_id;
        
        -- Buscar si la variante ya tiene opciones
        SELECT id INTO option_id_var
        FROM product_variant_options
        WHERE product_variant_id = variant_id_var
        LIMIT 1;
        
        -- Si no hay opciones, crear una opción "Default"
        IF option_id_var IS NULL THEN
            INSERT INTO product_variant_options (id, product_variant_id, name, stock, created_at)
            VALUES (gen_random_uuid(), variant_id_var, 'Default', 0, CURRENT_TIMESTAMP)
            RETURNING id INTO option_id_var;
        END IF;
        
        -- Actualizar el precio para asociarlo a la opción (usando product_variant_id para guardar el ID de la opción)
        UPDATE product_prices
        SET product_variant_id = option_id_var
        WHERE id = price_record.price_id;
    END LOOP;
END $$;

-- 3. Crear el nuevo foreign key constraint apuntando a product_variant_options
ALTER TABLE product_prices
ADD CONSTRAINT fk_product_prices_variant_option
FOREIGN KEY (product_variant_id) 
REFERENCES product_variant_options(id) 
ON DELETE CASCADE;

-- 4. Crear índice para mejorar el rendimiento
CREATE INDEX IF NOT EXISTS idx_product_prices_variant_id 
ON product_prices(product_variant_id);

-- 5. Comentarios para documentación
COMMENT ON COLUMN product_prices.product_variant_id IS 
'ID de la opción de variante asociada (de la tabla product_variant_options). Los precios ahora están asociados a opciones específicas, permitiendo diferentes precios por localidad para cada opción. Aunque la columna se llama product_variant_id, ahora apunta a product_variant_options.id.';
