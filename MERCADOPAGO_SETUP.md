# Configuración de MercadoPago

Este documento explica cómo configurar MercadoPago para los pagos con tarjeta en Bausing.

## Credenciales de Prueba

Para desarrollo y pruebas, usa estas credenciales de prueba de MercadoPago:

```env
MP_ACCESS_TOKEN=TEST-6103708889552760-020119-e487e24989b22c39d6d5f34743854b80-526482732
MP_PUBLIC_KEY=TEST-851528f1-2389-49c8-8d2c-0d809b869bc0
```

## Configuración en .env

Agrega estas variables a tu archivo `.env`:

```env
# MercadoPago
MP_ACCESS_TOKEN=TEST-6103708889552760-020119-e487e24989b22c39d6d5f34743854b80-526482732
MP_PUBLIC_KEY=TEST-851528f1-2389-49c8-8d2c-0d809b869bc0

# URLs (ajustar según tu entorno)
FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:5000
```

## Tarjetas de Prueba

Para probar los pagos, puedes usar estas tarjetas de prueba de MercadoPago:

### Tarjeta Aprobada
- **Número**: 5031 7557 3453 0604
- **CVV**: 123
- **Vencimiento**: 11/25
- **Nombre**: APRO

### Tarjeta Rechazada
- **Número**: 5031 4332 1540 6351
- **CVV**: 123
- **Vencimiento**: 11/25
- **Nombre**: OTHE

### Tarjeta Pendiente
- **Número**: 5031 7557 3453 0604
- **CVV**: 123
- **Vencimiento**: 11/25
- **Nombre**: CONT

## Flujo de Pago

1. El usuario selecciona "Tarjeta" como método de pago (sin marcar "Abonar al recibir")
2. Se crea la orden en el backend
3. El backend crea una preferencia de MercadoPago
4. El frontend redirige al usuario a MercadoPago
5. El usuario completa el pago en MercadoPago (puede elegir cuotas)
6. MercadoPago redirige de vuelta a `/checkout/success`
7. El webhook de MercadoPago notifica al backend cuando el pago es aprobado
8. El backend marca la orden como pagada

## Webhook

El webhook está configurado en:
- **Endpoint**: `/api/orders/webhooks/mercadopago`
- **URL completa**: `{BACKEND_URL}/api/orders/webhooks/mercadopago`

**Importante**: En producción, necesitarás configurar esta URL en el panel de MercadoPago para recibir las notificaciones de pago.

## Producción

Cuando estés listo para producción:

1. Obtén tus credenciales de producción desde el panel de MercadoPago
2. Reemplaza las credenciales de prueba en el `.env`:
   ```env
   MP_ACCESS_TOKEN=tu-access-token-de-produccion
   MP_PUBLIC_KEY=tu-public-key-de-produccion
   ```
3. Configura el webhook en el panel de MercadoPago con la URL de producción
4. Asegúrate de que `FRONTEND_URL` y `BACKEND_URL` apunten a tus URLs de producción

## Características Implementadas

- ✅ Checkout API de MercadoPago
- ✅ Soporte para hasta 12 cuotas
- ✅ Exclusión de tickets y ATMs (solo tarjetas)
- ✅ Webhook para notificaciones de pago
- ✅ Redirección automática después del pago
- ✅ Manejo de pagos aprobados, pendientes y rechazados
