-- Orden manual de las imágenes dentro de cada carrusel (hero_images.position = tipo de carrusel).
-- Se ordena por display_order ASC y, a igualdad, por created_at ASC.
ALTER TABLE hero_images ADD COLUMN IF NOT EXISTS display_order INTEGER NOT NULL DEFAULT 0;

-- Backfill: conserva el orden actual (created_at) dentro de cada position.
UPDATE hero_images h
SET display_order = r.rn
FROM (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY position ORDER BY created_at ASC) - 1 AS rn
    FROM hero_images
) r
WHERE h.id = r.id;
