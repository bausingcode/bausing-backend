-- Tabla: sugerencias PDP "Completa tu compra" (una fila por categoría principal; hasta 2 productos en uso, ver product_id_3 legacy).
-- Requiere PostgreSQL 13+ para gen_random_uuid(), o instalá: CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS category_pdp_cross_sell (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id UUID NOT NULL REFERENCES categories (id) ON DELETE CASCADE,
  product_id_1 UUID NULL REFERENCES products (id) ON DELETE SET NULL,
  product_id_2 UUID NULL REFERENCES products (id) ON DELETE SET NULL,
  product_id_3 UUID NULL REFERENCES products (id) ON DELETE SET NULL,
  updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
  updated_by UUID NULL REFERENCES admin_users (id) ON DELETE SET NULL,
  CONSTRAINT uq_category_pdp_cross_sell_category UNIQUE (category_id)
);

CREATE INDEX IF NOT EXISTS idx_category_pdp_cross_sell_category
  ON category_pdp_cross_sell (category_id);

-- Opcional: quitar configuración vieja en system_settings (ejecutar después de migrar datos si aplica).
-- DELETE FROM system_settings WHERE key = 'catalog.pdp_cross_sell_by_category';
