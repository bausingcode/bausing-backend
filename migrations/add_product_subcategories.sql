-- Migración: Agregar soporte para múltiples subcategorías por producto
-- Descripción: Permite que un producto tenga una categoría padre (category_id) 
--              y múltiples subcategorías asociadas a través de una tabla de relación

-- 1. Crear tabla de relación muchos-a-muchos entre productos y subcategorías
CREATE TABLE IF NOT EXISTS product_subcategories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    subcategory_id UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    category_option_id UUID REFERENCES category_options(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Asegurar que una subcategoría solo se asocie una vez a un producto
    UNIQUE(product_id, subcategory_id)
);

-- 2. Crear índices para mejorar el rendimiento de las consultas
CREATE INDEX IF NOT EXISTS idx_product_subcategories_product_id ON product_subcategories(product_id);
CREATE INDEX IF NOT EXISTS idx_product_subcategories_subcategory_id ON product_subcategories(subcategory_id);
CREATE INDEX IF NOT EXISTS idx_product_subcategories_category_option_id ON product_subcategories(category_option_id);

-- 3. Migrar datos existentes (si hay productos con category_id que es una subcategoría)
-- Esto migra los productos que tienen un category_id que apunta a una subcategoría
-- a la nueva tabla product_subcategories, y actualiza category_id al parent_id
DO $$
DECLARE
    product_record RECORD;
    parent_category_id UUID;
BEGIN
    -- Para cada producto que tiene un category_id que es una subcategoría
    FOR product_record IN 
        SELECT p.id, p.category_id 
        FROM products p
        INNER JOIN categories c ON p.category_id = c.id
        WHERE c.parent_id IS NOT NULL
    LOOP
        -- Obtener el parent_id de la categoría (que es la categoría padre)
        SELECT parent_id INTO parent_category_id
        FROM categories
        WHERE id = product_record.category_id;
        
        -- Insertar en product_subcategories
        INSERT INTO product_subcategories (product_id, subcategory_id)
        VALUES (product_record.id, product_record.category_id)
        ON CONFLICT (product_id, subcategory_id) DO NOTHING;
        
        -- Actualizar category_id al parent_id
        UPDATE products
        SET category_id = parent_category_id
        WHERE id = product_record.id;
    END LOOP;
END $$;

-- 4. Comentarios para documentación
COMMENT ON TABLE product_subcategories IS 'Tabla de relación muchos-a-muchos entre productos y subcategorías. Permite que un producto tenga múltiples subcategorías asociadas.';
COMMENT ON COLUMN product_subcategories.product_id IS 'ID del producto';
COMMENT ON COLUMN product_subcategories.subcategory_id IS 'ID de la subcategoría (debe ser una categoría con parent_id)';
COMMENT ON COLUMN product_subcategories.category_option_id IS 'ID de la opción de categoría seleccionada para esta subcategoría (opcional)';
