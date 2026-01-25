-- Optimización de índices para queries de productos con localidad
-- Ejecutar este script para mejorar el rendimiento de las consultas

-- Índice compuesto para product_prices con locality_id (query más común)
CREATE INDEX IF NOT EXISTS idx_product_prices_locality_variant 
ON product_prices(locality_id, product_variant_id);

-- Índice para product_variant_options con product_variant_id
CREATE INDEX IF NOT EXISTS idx_product_variant_options_variant_id 
ON product_variant_options(product_variant_id);

-- Índice para product_variants con product_id
CREATE INDEX IF NOT EXISTS idx_product_variants_product_id 
ON product_variants(product_id);

-- Índice compuesto para productos activos (usado frecuentemente)
CREATE INDEX IF NOT EXISTS idx_products_active_created 
ON products(is_active, created_at DESC) 
WHERE is_active = true;

-- Índice para imágenes de productos ordenadas por posición
CREATE INDEX IF NOT EXISTS idx_product_images_product_position 
ON product_images(product_id, position);

-- Índice para homepage_distribution con product_id (para joins más rápidos)
CREATE INDEX IF NOT EXISTS idx_homepage_distribution_product_section 
ON homepage_product_distribution(product_id, section) 
WHERE product_id IS NOT NULL;

-- Analizar tablas para actualizar estadísticas
ANALYZE products;
ANALYZE product_variants;
ANALYZE product_variant_options;
ANALYZE product_prices;
ANALYZE product_images;
ANALYZE homepage_product_distribution;

-- Comentarios
COMMENT ON INDEX idx_product_prices_locality_variant IS 'Optimiza queries de precios filtrados por localidad';
COMMENT ON INDEX idx_product_variant_options_variant_id IS 'Optimiza joins entre variants y options';
COMMENT ON INDEX idx_product_variants_product_id IS 'Optimiza joins entre products y variants';
COMMENT ON INDEX idx_products_active_created IS 'Optimiza queries de productos activos ordenados por fecha';
COMMENT ON INDEX idx_product_images_product_position IS 'Optimiza queries de imágenes ordenadas por posición';
COMMENT ON INDEX idx_homepage_distribution_product_section IS 'Optimiza queries de distribución de homepage';
