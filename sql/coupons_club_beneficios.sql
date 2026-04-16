-- Cupones: restricción exclusiva para productos del Club Beneficios.
-- Ejecutá esto sobre la base existente. Si tu tabla `coupons` ya tiene columnas
-- equivalentes, adaptá nombres o omití las líneas que fallen.

-- 1) Marca de alcance (checkout / carrito debe rechazar si el carrito no es 100% club)
ALTER TABLE coupons
  ADD COLUMN IF NOT EXISTS club_beneficios_only boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN coupons.club_beneficios_only IS
  'Si es true, el cupón solo puede aplicarse cuando todos los ítems son productos en club_beneficios_items.';

-- 2) Columnas típicas si la tabla fue creada mínima o incompleta (ignorá errores "already exists")
-- Nota: el ORM actual no mapea `description`; si la querés, agregá la columna y el campo en el modelo.
ALTER TABLE coupons ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE coupons ADD COLUMN IF NOT EXISTS discount_type varchar(20) NOT NULL DEFAULT 'percentage';
ALTER TABLE coupons ADD COLUMN IF NOT EXISTS discount_value numeric(12, 2) NOT NULL DEFAULT 0;
ALTER TABLE coupons ADD COLUMN IF NOT EXISTS max_uses integer;
ALTER TABLE coupons ADD COLUMN IF NOT EXISTS uses_count integer NOT NULL DEFAULT 0;
ALTER TABLE coupons ADD COLUMN IF NOT EXISTS valid_from timestamptz;
ALTER TABLE coupons ADD COLUMN IF NOT EXISTS valid_until timestamptz;
ALTER TABLE coupons ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;
ALTER TABLE coupons ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();

-- 3) Índice único insensible a mayúsculas en el código (opcional; el backend también normaliza)
CREATE UNIQUE INDEX IF NOT EXISTS coupons_code_lower_idx ON coupons (lower(code));

-- Si preferís crear la tabla desde cero (solo cuando no exista):
-- CREATE TABLE coupons (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   code varchar(64) NOT NULL,
--   description text,
--   discount_type varchar(20) NOT NULL DEFAULT 'percentage',
--   discount_value numeric(12, 2) NOT NULL,
--   max_uses integer,
--   uses_count integer NOT NULL DEFAULT 0,
--   valid_from timestamptz,
--   valid_until timestamptz,
--   is_active boolean NOT NULL DEFAULT true,
--   club_beneficios_only boolean NOT NULL DEFAULT false,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   CONSTRAINT coupons_code_lower_uniq UNIQUE (lower(code))
-- );
