-- Preguntas frecuentes gestionables desde el admin.
-- Ejecutar una vez contra la base del ecommerce.

CREATE TABLE IF NOT EXISTS faq_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_published BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_faq_items_published_sort
    ON faq_items (is_published, sort_order, id);

COMMENT ON TABLE faq_items IS 'FAQ del sitio; el sitio público solo lista filas con is_published = true ordenadas por sort_order.';
