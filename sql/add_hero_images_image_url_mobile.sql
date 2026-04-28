-- Imagen opcional solo para viewport móvil (hero principal, proporción vertical).
ALTER TABLE hero_images
  ADD COLUMN IF NOT EXISTS image_url_mobile TEXT;
