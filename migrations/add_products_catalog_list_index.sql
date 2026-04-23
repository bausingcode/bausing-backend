-- Acelera listados de vitrina: filtros típicos + ORDER BY created_at
-- Ejecutar una vez en PostgreSQL (psql, DBeaver, o migración manual)
CREATE INDEX IF NOT EXISTS ix_products_ecom_list
  ON products (is_active, crm_product_id, category_id, created_at DESC);

COMMENT ON INDEX ix_products_ecom_list IS
  'Catálogo: productos activos con CRM, por categoría y orden por fecha.';
