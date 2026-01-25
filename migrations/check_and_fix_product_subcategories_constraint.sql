-- Script para verificar y corregir los constraints de product_subcategories
-- Este script primero verifica qué constraints existen y luego los elimina/recrea según sea necesario

-- 1. Eliminar TODOS los posibles constraints únicos antiguos
DO $$
DECLARE
    constraint_record RECORD;
BEGIN
    -- Buscar todos los constraints únicos en product_subcategories que solo incluyan product_id y subcategory_id
    FOR constraint_record IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'product_subcategories'::regclass
        AND contype = 'u'
        AND (
            conname = 'unique_product_subcategory' OR
            conname = 'product_subcategories_product_id_subcategory_id_key' OR
            conname LIKE '%product_id%subcategory_id%'
        )
    LOOP
        EXECUTE 'ALTER TABLE product_subcategories DROP CONSTRAINT IF EXISTS ' || quote_ident(constraint_record.conname);
        RAISE NOTICE 'Eliminado constraint: %', constraint_record.conname;
    END LOOP;
END $$;

-- 2. Eliminar el nuevo constraint si ya existe
ALTER TABLE product_subcategories
DROP CONSTRAINT IF EXISTS unique_product_subcategory_option;

-- 3. Crear el nuevo constraint único que incluye category_option_id
ALTER TABLE product_subcategories
ADD CONSTRAINT unique_product_subcategory_option 
UNIQUE(product_id, subcategory_id, category_option_id);

-- 4. Comentarios actualizados
COMMENT ON CONSTRAINT unique_product_subcategory_option ON product_subcategories IS 
'Permite múltiples opciones para la misma subcategoría, asegurando que cada combinación de (producto, subcategoría, opción) sea única. Si category_option_id es NULL, solo puede haber un registro sin opción por (product_id, subcategory_id).';
