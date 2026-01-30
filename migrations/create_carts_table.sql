-- Migración: Crear tabla de carritos
-- Descripción: Crea la tabla carts para registrar cuando un usuario crea un carrito por primera vez

CREATE TABLE IF NOT EXISTS carts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Crear índice para mejorar el rendimiento de búsquedas por user_id
CREATE INDEX IF NOT EXISTS idx_carts_user_id ON carts(user_id);

-- Crear índice para mejorar el rendimiento de búsquedas por created_at
CREATE INDEX IF NOT EXISTS idx_carts_created_at ON carts(created_at);
