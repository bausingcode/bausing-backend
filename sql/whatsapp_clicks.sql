CREATE TABLE IF NOT EXISTS whatsapp_clicks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  click_type VARCHAR(20) NOT NULL,
  page VARCHAR(255),
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_whatsapp_clicks_type_created_at
  ON whatsapp_clicks (click_type, created_at);
