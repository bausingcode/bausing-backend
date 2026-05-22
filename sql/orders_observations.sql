-- Observaciones de checkout (cuotas, tarjeta, banco, notas del cliente)
ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS observations TEXT;
