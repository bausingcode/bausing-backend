-- Migración: Actualizar product_subcategories para soportar múltiples opciones por subcategoría
-- Descripción: Modifica el constraint único para permitir múltiples registros de la misma subcategoría
--              con diferentes opciones, cambiando de (product_id, subcategory_id) a (product_id, subcategory_id, category_option_id)
-- Esta migración es idempotente: se puede ejecutar múltiples veces sin error

-- 1. Eliminar todos los constraints únicos antiguos (pueden tener diferentes nombres)
-- Estos son los posibles nombres que puede tener el constraint:
-- - unique_product_subcategory (nombre explícito en la migración original)
-- - product_subcategories_product_id_subcategory_id_key (nombre por defecto de PostgreSQL)
-- - Cualquier otro constraint único que incluya solo (product_id, subcategory_id)
ALTER TABLE product_subcategories 
DROP CONSTRAINT IF EXISTS unique_product_subcategory;

ALTER TABLE product_subcategories
DROP CONSTRAINT IF EXISTS product_subcategories_product_id_subcategory_id_key;

-- 2. Eliminar el nuevo constraint si ya existe (para poder recrearlo)
ALTER TABLE product_subcategories
DROP CONSTRAINT IF EXISTS unique_product_subcategory_option;

-- 3. Crear nuevo constraint único que incluye category_option_id
-- Esto permite múltiples opciones para la misma subcategoría
ALTER TABLE product_subcategories
ADD CONSTRAINT unique_product_subcategory_option 
UNIQUE(product_id, subcategory_id, category_option_id);

-- 4. Comentarios actualizados
COMMENT ON CONSTRAINT unique_product_subcategory_option ON product_subcategories IS 
'Permite múltiples opciones para la misma subcategoría, asegurando que cada combinación de (producto, subcategoría, opción) sea única. Si category_option_id es NULL, solo puede haber un registro sin opción por (product_id, subcategory_id).';
