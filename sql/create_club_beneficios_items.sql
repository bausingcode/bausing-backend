-- Tabla para los productos del Club Beneficios (orden de la landing pública).
-- Ejecutar una sola vez sobre la base existente.

CREATE TABLE IF NOT EXISTS club_beneficios_items (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    position    integer     NOT NULL,
    product_id  uuid        NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_club_beneficios_position   UNIQUE (position),
    CONSTRAINT uq_club_beneficios_product_id UNIQUE (product_id)
);
