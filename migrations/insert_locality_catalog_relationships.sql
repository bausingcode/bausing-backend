-- Migración: Insertar relaciones entre localidades y catálogos
-- Descripción: Asocia cada localidad con su catálogo correspondiente según el mapeo exacto de la tabla
-- IMPORTANTE: Este script debe ejecutarse después de tener las localidades y catálogos en la base de datos

-- Primero obtenemos los IDs de los catálogos
DO $$
DECLARE
    catalog_cordoba_capital_id UUID;
    catalog_provincia_cordoba_id UUID;
    catalog_mendoza_id UUID;
    catalog_la_pampa_id UUID;
    catalog_provincias_seleccionadas_id UUID;
BEGIN
    -- Obtener IDs de los catálogos
    SELECT id INTO catalog_cordoba_capital_id FROM catalogs WHERE name = 'Cordoba capital' LIMIT 1;
    SELECT id INTO catalog_provincia_cordoba_id FROM catalogs WHERE name = 'Provincia de cordoba' LIMIT 1;
    SELECT id INTO catalog_mendoza_id FROM catalogs WHERE name = 'Mendoza' LIMIT 1;
    SELECT id INTO catalog_la_pampa_id FROM catalogs WHERE name = 'La pampa' LIMIT 1;
    SELECT id INTO catalog_provincias_seleccionadas_id FROM catalogs WHERE name = 'Provincias seleccionadas' LIMIT 1;

    -- Insertar relaciones usando los IDs específicos de las localidades según la tabla
    
    -- Provincia de cordoba
    INSERT INTO locality_catalogs (locality_id, catalog_id) VALUES
        ('305fe310-1356-468e-b738-a18a51292276', catalog_provincia_cordoba_id),
        ('e8ac78eb-bbcc-416a-a5fd-a58e2ebae127', catalog_provincia_cordoba_id),
        ('1cb64fe8-2c6e-42c1-8b5e-133e5f63f7c1', catalog_provincia_cordoba_id),
        ('96b08cff-f9b6-40b5-b33f-1bb1fbd99fed', catalog_provincia_cordoba_id),
        ('d0afe008-ab1e-4ffc-9bf5-e0370a77339c', catalog_provincia_cordoba_id),
        ('df394132-221d-4936-b3f6-3ff8e813c617', catalog_provincia_cordoba_id),
        ('03f26a5e-dc99-47d4-8a1a-858536ba0c72', catalog_provincia_cordoba_id),
        ('dfaed016-ac8c-4a14-b2b9-033822ccd0d5', catalog_provincia_cordoba_id),
        ('f37976c9-0949-4f20-ad93-9e3a66a7c392', catalog_provincia_cordoba_id),
        ('b3de0743-8727-4a85-a1ea-76f6aa556009', catalog_provincia_cordoba_id)
    ON CONFLICT (locality_id, catalog_id) DO NOTHING;

    -- Cordoba capital
    INSERT INTO locality_catalogs (locality_id, catalog_id) VALUES
        ('39acf5ca-28d1-4300-b009-07c675c45073', catalog_cordoba_capital_id),
        ('9a8ed3c6-65b7-4af4-97de-be220f70c21d', catalog_cordoba_capital_id),
        ('a93f5c4d-83c3-4dcf-9788-cff283e8f5ab', catalog_cordoba_capital_id),
        ('9d5ff190-34bc-4d0e-a53c-b228c8e000cd', catalog_cordoba_capital_id),
        ('ac4ceada-74f6-4f10-8a53-4abb334fe312', catalog_cordoba_capital_id),
        ('f6b8a63c-721f-4f9b-95df-ce84f8b674e7', catalog_cordoba_capital_id)
    ON CONFLICT (locality_id, catalog_id) DO NOTHING;

    -- Mendoza
    INSERT INTO locality_catalogs (locality_id, catalog_id) VALUES
        ('75db1388-4d56-4327-a6d9-519f8e6edf8e', catalog_mendoza_id),
        ('ee9221bd-620e-422b-9040-374d06f5b956', catalog_mendoza_id)
    ON CONFLICT (locality_id, catalog_id) DO NOTHING;

    -- La pampa
    INSERT INTO locality_catalogs (locality_id, catalog_id) VALUES
        ('a0f00a9b-b671-4d27-ae61-f1dd3c7acff9', catalog_la_pampa_id)
    ON CONFLICT (locality_id, catalog_id) DO NOTHING;

    -- Provincias seleccionadas
    INSERT INTO locality_catalogs (locality_id, catalog_id) VALUES
        ('184b23d6-8965-4ccf-82cc-35b35bac9a12', catalog_provincias_seleccionadas_id),
        ('7d1d008e-c15d-4ad0-a737-1904db764e70', catalog_provincias_seleccionadas_id),
        ('d256ca48-9302-45ba-9b77-1b50ef1ff0e4', catalog_provincias_seleccionadas_id),
        ('956018c5-7afa-4c03-b871-da4dec20c728', catalog_provincias_seleccionadas_id),
        ('0174fedf-4134-40a5-aac0-9d8856afcd42', catalog_provincias_seleccionadas_id),
        ('f0f45879-bfcf-432d-a6db-39d2d60a9822', catalog_provincias_seleccionadas_id),
        ('21778c0a-35b9-44c3-8d7d-629233eca1b7', catalog_provincias_seleccionadas_id),
        ('7a8fc409-fa4b-49ce-9878-ecff1045c832', catalog_provincias_seleccionadas_id),
        ('85c36b23-814d-4a17-84c2-9d927205842a', catalog_provincias_seleccionadas_id),
        ('8fd9014e-5291-46e4-b003-5e0891b38399', catalog_provincias_seleccionadas_id),
        ('dec0c267-e48a-450c-94d2-a81ea1be129d', catalog_provincias_seleccionadas_id)
    ON CONFLICT (locality_id, catalog_id) DO NOTHING;

END $$;

-- Para verificar las relaciones creadas:
-- SELECT c.name as catalog, l.name as locality, l.id as locality_id
-- FROM locality_catalogs lc
-- JOIN catalogs c ON lc.catalog_id = c.id
-- JOIN localities l ON lc.locality_id = l.id
-- ORDER BY c.name, l.name;
