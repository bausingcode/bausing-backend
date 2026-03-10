-- Migración: Sistema de Referidos (Programa de Afiliados)
-- Fecha: 2025-01-XX
-- Descripción: Agrega sistema completo de referidos con códigos únicos, tracking de referidos y acreditación de Pesos Bausing

-- ============================================
-- 1. Agregar columna referral_code a users
-- ============================================
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS referral_code VARCHAR(20) UNIQUE;

-- Crear índice para búsquedas rápidas
CREATE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code);

-- ============================================
-- 2. Agregar columna referral_code_used a orders
-- ============================================
ALTER TABLE orders 
ADD COLUMN IF NOT EXISTS referral_code_used VARCHAR(20);

-- Crear índice para búsquedas rápidas
CREATE INDEX IF NOT EXISTS idx_orders_referral_code_used ON orders(referral_code_used);

-- ============================================
-- 3. Crear tabla referrals
-- ============================================
CREATE TABLE IF NOT EXISTS referrals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    referred_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    credit_amount NUMERIC(10, 2) NOT NULL,
    credited BOOLEAN DEFAULT FALSE,
    credited_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(order_id) -- Una orden solo puede generar un referido
);

-- Crear índices para búsquedas rápidas
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);
CREATE INDEX IF NOT EXISTS idx_referrals_referred ON referrals(referred_id);
CREATE INDEX IF NOT EXISTS idx_referrals_order ON referrals(order_id);
CREATE INDEX IF NOT EXISTS idx_referrals_credited ON referrals(credited);

-- ============================================
-- 4. Agregar configuraciones del sistema
-- ============================================
INSERT INTO system_settings (id, key, value, value_type, category, description, created_at)
VALUES 
    (gen_random_uuid(), 'referral.credit_type', 'fixed', 'string', 'referral', 'Tipo de crédito: fixed o percentage', NOW()),
    (gen_random_uuid(), 'referral.credit_amount', '500', 'number', 'referral', 'Monto fijo de crédito por referido', NOW()),
    (gen_random_uuid(), 'referral.percentage', '5', 'number', 'referral', 'Porcentaje del total si credit_type es percentage', NOW())
ON CONFLICT (key) DO NOTHING;

-- ============================================
-- Comentarios para documentación
-- ============================================
COMMENT ON COLUMN users.referral_code IS 'Código único de referido del usuario';
COMMENT ON COLUMN orders.referral_code_used IS 'Código de referido usado en esta orden';
COMMENT ON TABLE referrals IS 'Registro de referidos y créditos otorgados';
COMMENT ON COLUMN referrals.referrer_id IS 'Usuario que refirió (gana el crédito)';
COMMENT ON COLUMN referrals.referred_id IS 'Usuario referido (hizo la compra)';
COMMENT ON COLUMN referrals.order_id IS 'Orden que activó el referido';
COMMENT ON COLUMN referrals.credit_amount IS 'Monto de Pesos Bausing acreditado';
COMMENT ON COLUMN referrals.credited IS 'Indica si ya se acreditó el crédito';
COMMENT ON COLUMN referrals.credited_at IS 'Fecha y hora de acreditación del crédito';
