-- Ocultar filas en el admin en "Productos no completados" y combos pendientes (listado Combos), sin borrarlas del CRM.
-- Ejecutar una vez antes o junto al deploy del feature.

ALTER TABLE crm_products
  ADD COLUMN IF NOT EXISTS hidden_from_not_completed_list BOOLEAN NOT NULL DEFAULT false;

UPDATE crm_products
SET hidden_from_not_completed_list = false
WHERE hidden_from_not_completed_list IS NULL;
