-- Crear tabla para distribución de productos en el inicio
CREATE TABLE IF NOT EXISTS homepage_product_distribution (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section VARCHAR(50) NOT NULL CHECK (section IN ('featured', 'discounts', 'mattresses', 'complete_purchase')),
    position INTEGER NOT NULL CHECK (position >= 0),
    product_id UUID REFERENCES products(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(section, position)
);

-- Crear índices para mejorar el rendimiento
CREATE INDEX IF NOT EXISTS idx_homepage_distribution_section ON homepage_product_distribution(section);
CREATE INDEX IF NOT EXISTS idx_homepage_distribution_product ON homepage_product_distribution(product_id);
CREATE INDEX IF NOT EXISTS idx_homepage_distribution_section_position ON homepage_product_distribution(section, position);

-- Comentarios para documentación
COMMENT ON TABLE homepage_product_distribution IS 'Distribución de productos en la página de inicio';
COMMENT ON COLUMN homepage_product_distribution.section IS 'Sección: featured (4 productos), discounts (3 productos), mattresses (4 productos), complete_purchase (4 productos)';
COMMENT ON COLUMN homepage_product_distribution.position IS 'Posición dentro de la sección (0-indexed)';
COMMENT ON COLUMN homepage_product_distribution.product_id IS 'ID del producto a mostrar en esta posición (NULL si está vacío)';
