-- Migración: Crear tabla de catálogos y relación con localidades
-- Descripción: Crea el sistema de catálogos para agrupar localidades y permitir precios por catálogo

-- 1. Crear tabla de catálogos
CREATE TABLE IF NOT EXISTS catalogs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- 2. Crear tabla de relación entre localidades y catálogos
CREATE TABLE IF NOT EXISTS locality_catalogs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    locality_id UUID NOT NULL REFERENCES localities(id) ON DELETE CASCADE,
    catalog_id UUID NOT NULL REFERENCES catalogs(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(locality_id, catalog_id)
);

-- 3. Crear índices para mejorar el rendimiento
CREATE INDEX IF NOT EXISTS idx_locality_catalogs_locality_id ON locality_catalogs(locality_id);
CREATE INDEX IF NOT EXISTS idx_locality_catalogs_catalog_id ON locality_catalogs(catalog_id);

-- 4. Insertar los 5 catálogos iniciales
INSERT INTO catalogs (id, name, description) VALUES
    (gen_random_uuid(), 'Cordoba capital', 'Catálogo para Córdoba Capital'),
    (gen_random_uuid(), 'Provincia de cordoba', 'Catálogo para Provincia de Córdoba'),
    (gen_random_uuid(), 'Mendoza', 'Catálogo para Mendoza'),
    (gen_random_uuid(), 'La pampa', 'Catálogo para La Pampa'),
    (gen_random_uuid(), 'Provincias seleccionadas', 'Catálogo para Provincias Seleccionadas')
ON CONFLICT (name) DO NOTHING;
