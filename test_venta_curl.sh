#!/bin/bash

# Curl de prueba para crear una venta en autogestión
# Endpoint: /api/ventas/crear
# Base URL: https://autogestion.bausing.com.ar/api/ventas
# Documentación: Ver docs/API_VENTAS.md

curl -X POST "https://pruebas.bausing.com.ar/api/ventas/crear" \
  -H "Authorization: Bearer {api_secret}" \
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
