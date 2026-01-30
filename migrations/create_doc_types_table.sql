-- Migración: Crear tabla de tipos de documento
-- Descripción: Crea la tabla doc_types para almacenar los tipos de documento disponibles

CREATE TABLE IF NOT EXISTS doc_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    crm_doc_type_id UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Crear índices para mejorar el rendimiento
CREATE INDEX IF NOT EXISTS idx_doc_types_code ON doc_types(code);
CREATE INDEX IF NOT EXISTS idx_doc_types_name ON doc_types(name);
