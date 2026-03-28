-- Run once on production/staging before deploying draft feature.
-- Adds is_draft and a unique index per (section, position, is_draft).

ALTER TABLE homepage_product_distribution
  ADD COLUMN IF NOT EXISTS is_draft BOOLEAN NOT NULL DEFAULT false;

UPDATE homepage_product_distribution
SET is_draft = false
WHERE is_draft IS NULL;

-- Legacy installs may have UNIQUE (section, position) — drop so draft + published can coexist.
ALTER TABLE homepage_product_distribution
  DROP CONSTRAINT IF EXISTS homepage_product_distribution_section_position_key;

ALTER TABLE homepage_product_distribution
  DROP CONSTRAINT IF EXISTS homepage_product_distribution_section_position_unique;

CREATE UNIQUE INDEX IF NOT EXISTS uq_homepage_dist_section_slot_draft
  ON homepage_product_distribution (section, "position", is_draft);
