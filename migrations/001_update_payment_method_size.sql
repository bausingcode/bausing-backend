-- Migración: Actualizar tamaño de payment_method para soportar múltiples métodos de pago
-- Fecha: 2024
-- Descripción: Cambia payment_method de VARCHAR(50) a VARCHAR(200) para permitir valores como "card,wallet"

-- Actualizar tabla orders
ALTER TABLE orders 
ALTER COLUMN payment_method TYPE VARCHAR(200);

-- Actualizar tabla sale_retry_queue
ALTER TABLE sale_retry_queue 
ALTER COLUMN payment_method TYPE VARCHAR(200);

-- Verificar los cambios
SELECT 
    table_name,
    column_name,
    data_type,
    character_maximum_length
FROM information_schema.columns
WHERE table_name IN ('orders', 'sale_retry_queue')
  AND column_name = 'payment_method';
