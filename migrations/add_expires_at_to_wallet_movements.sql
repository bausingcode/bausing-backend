-- Migration: Add expires_at column to wallet_movements table
-- This migration adds the expires_at column to track when wallet credits expire
-- based on the system configuration (wallet.expiration_days)

-- Add expires_at column to wallet_movements table
ALTER TABLE wallet_movements 
ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP NULL;

-- Add index for better query performance when filtering by expiration
CREATE INDEX IF NOT EXISTS idx_wallet_movements_expires_at 
ON wallet_movements(expires_at) 
WHERE expires_at IS NOT NULL;

-- Add index for querying valid (non-expired) credits
CREATE INDEX IF NOT EXISTS idx_wallet_movements_valid_credits 
ON wallet_movements(wallet_id, expires_at) 
WHERE amount > 0 AND (expires_at IS NULL OR expires_at > NOW());

-- Comment on column
COMMENT ON COLUMN wallet_movements.expires_at IS 'Fecha de vencimiento del movimiento. Solo aplica para créditos. NULL significa sin vencimiento.';

