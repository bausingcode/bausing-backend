#!/bin/bash

# ============================================================================
# Ejemplos de Curl para crear ventas en autogestión
# Base URL: https://autogestion.bausing.com.ar/api/ventas
# Documentación completa: Ver docs/API_VENTAS.md
# ============================================================================

# Reemplazar {api_secret} con tu token real de autenticación
API_SECRET="{api_secret}"

# ============================================================================
# Ejemplo 1: Venta con DNI (tipo_documento_cliente = 1)
# ============================================================================
echo "Ejemplo 1: Venta con DNI"
curl -X POST "https://autogestion.bausing.com.ar/api/ventas/crear" \
  -H "Authorization: Bearer $API_SECRET" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "fecha_detalle": "2024-01-15",
    "tipo_venta": 1,
    "cliente_nombre": "Juan Pérez",
    "cliente_direccion": "Calle Falsa 123",
    "cliente_direccion_barrio": "Centro",
    "cliente_direccion_mas_datos": "Piso 2, Dpto A",
    "tipo_documento_cliente": 1,
    "documento_cliente": "12345678",
    "cliente_telefono": "011-1234-5678",
    "cel_alternativo": "011-9876-5432",
    "email_cliente": "cliente@example.com",
    "provincia_id": 1,
    "localidad": "Buenos Aires",
    "zona_id": 3,
    "observaciones": "Observaciones de la venta",
    "lat_long": {
      "latitud": -34.603722,
      "longitud": -58.381592
    },
    "js": [
      {
        "id": null,
        "accion": "N",
        "item_id": 123,
        "cantidad_recibida": 2,
        "precio": 200.00,
        "unitario_sin_fpago": 100.00,
        "descripcion": "Producto Ejemplo"
      }
    ],
    "formaPagos": [
      {
        "medios_pago_id": 1,
        "monto_total": 200.00,
        "procesado": true,
        "numero_comprobante": "123456",
        "fecha_cobranza": "2024-01-15"
      }
    ]
  }'

echo -e "\n\n"

# ============================================================================
# Ejemplo 2: Venta con CUIT (tipo_documento_cliente = 2)
# IMPORTANTE: Requiere email_cliente
# ============================================================================
echo "Ejemplo 2: Venta con CUIT"
curl -X POST "https://autogestion.bausing.com.ar/api/ventas/crear" \
  -H "Authorization: Bearer $API_SECRET" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "fecha_detalle": "2024-01-15",
    "tipo_venta": 1,
    "cliente_nombre": "Empresa S.A.",
    "cliente_direccion": "Av. Corrientes 1234",
    "cliente_direccion_barrio": "Microcentro",
    "tipo_documento_cliente": 2,
    "documento_cliente": "20-12345678-9",
    "cliente_telefono": "011-4321-5678",
    "email_cliente": "empresa@example.com",
    "provincia_id": 1,
    "localidad": "Buenos Aires",
    "zona_id": 3,
    "js": [
      {
        "id": null,
        "accion": "N",
        "item_id": 456,
        "cantidad_recibida": 1,
        "precio": 150.00,
        "unitario_sin_fpago": 150.00,
        "descripcion": "Otro Producto"
      }
    ],
    "formaPagos": [
      {
        "medios_pago_id": 2,
        "monto_total": 150.00,
        "procesado": false
      }
    ]
  }'

echo -e "\n\n"

# ============================================================================
# Ejemplo 3: Venta con múltiples productos y múltiples formas de pago
# ============================================================================
echo "Ejemplo 3: Venta con múltiples productos y pagos"
curl -X POST "https://autogestion.bausing.com.ar/api/ventas/crear" \
  -H "Authorization: Bearer $API_SECRET" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "fecha_detalle": "2024-01-15",
    "tipo_venta": 1,
    "cliente_nombre": "María González",
    "cliente_direccion": "Calle San Martín 456",
    "tipo_documento_cliente": 1,
    "documento_cliente": "98765432",
    "cliente_telefono": "011-5555-1234",
    "email_cliente": "maria@example.com",
    "provincia_id": 1,
    "localidad": "Buenos Aires",
    "zona_id": 3,
    "js": [
      {
        "id": null,
        "accion": "N",
        "item_id": 123,
        "cantidad_recibida": 2,
        "precio": 200.00,
        "unitario_sin_fpago": 100.00,
        "descripcion": "Producto Ejemplo"
      },
      {
        "id": null,
        "accion": "N",
        "item_id": 456,
        "cantidad_recibida": 1,
        "precio": 150.00,
        "unitario_sin_fpago": 150.00,
        "descripcion": "Otro Producto"
      }
    ],
    "formaPagos": [
      {
        "medios_pago_id": 1,
        "monto_total": 200.00,
        "procesado": true,
        "numero_comprobante": "123456",
        "fecha_cobranza": "2024-01-15"
      },
      {
        "medios_pago_id": 2,
        "monto_total": 150.00,
        "procesado": false
      }
    ]
  }'

echo -e "\n\n"

# ============================================================================
# NOTAS IMPORTANTES:
# ============================================================================
# 1. Reemplazar {api_secret} con tu token real
# 2. Los campos vendedor_id, numero_comprobante, publicidad se asignan automáticamente
# 3. La suma de monto_total en formaPagos debe igualar la suma de precio en js
# 4. Para CUIT: formato debe ser XX-XXXXXXXX-X (13 caracteres con guiones)
# 5. Para CUIT: email_cliente es REQUERIDO
# 6. Para DNI: solo números, sin letras, puntos o espacios
# 7. Los item_id, provincia_id, zona_id, medios_pago_id deben existir en la BD
# ============================================================================
