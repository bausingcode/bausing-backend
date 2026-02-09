# Postman Collection - Reviews Reminders

Esta colección contiene el endpoint para enviar recordatorios de reseñas por email.

## Configuración

1. Importa el archivo `Reviews_Reminders.postman_collection.json` en Postman
2. Configura la variable `base_url` según tu entorno:
   - Desarrollo local: `http://localhost:5050`
   - Producción: `https://api.tudominio.com`

## Endpoint

### POST /api/reviews/send-reminders

**Descripción:** Envía emails de recordatorio a usuarios que tienen órdenes finalizadas sin reseñar y que pasaron más de 5 días desde la finalización.

**Autenticación:** Requiere API_KEY del .env. Debe enviarse en el header:
- `X-API-Key: tu-api-key-del-env`
- O `Authorization: Bearer tu-api-key-del-env`

**Request Body:** No requiere body

**Respuesta exitosa (200):**
```json
{
  "success": true,
  "message": "Proceso completado. 5 emails enviados, 0 fallidos",
  "emails_sent": 5,
  "emails_failed": 0,
  "users_notified": 5
}
```

**Respuesta de error de autenticación (401):**
```json
{
  "success": false,
  "error": "API key requerida. Proporciona X-API-Key en el header o Authorization: Bearer <key>"
}
```

**Respuesta de error (500):**
```json
{
  "success": false,
  "error": "Error al enviar recordatorios: ..."
}
```

## Uso en Cron Job

Este endpoint debe ser llamado periódicamente por un cron job. Ejemplos:

### Linux/Mac (crontab)
```bash
# Ejecutar todos los días a las 9:00 AM
# Usando X-API-Key header
0 9 * * * curl -X POST -H "X-API-Key: tu-api-key-del-env" http://localhost:5050/api/reviews/send-reminders

# O usando Authorization Bearer
0 9 * * * curl -X POST -H "Authorization: Bearer tu-api-key-del-env" http://localhost:5050/api/reviews/send-reminders
```

### Usando Node.js (node-cron)
```javascript
const cron = require('node-cron');
const axios = require('axios');

// Ejecutar todos los días a las 9:00 AM
cron.schedule('0 9 * * *', async () => {
  try {
    const response = await axios.post(
      'http://localhost:5050/api/reviews/send-reminders',
      {},
      {
        headers: {
          'X-API-Key': process.env.API_KEY // O usar Authorization: Bearer
        }
      }
    );
    console.log('Reminders sent:', response.data);
  } catch (error) {
    console.error('Error sending reminders:', error);
  }
});
```

### Usando Python (schedule)
```python
import schedule
import requests
import os
import time

def send_review_reminders():
    try:
        api_key = os.getenv('API_KEY')
        response = requests.post(
            'http://localhost:5050/api/reviews/send-reminders',
            headers={'X-API-Key': api_key}  # O usar Authorization: Bearer
        )
        print('Reminders sent:', response.json())
    except Exception as e:
        print('Error sending reminders:', e)

# Ejecutar todos los días a las 9:00 AM
schedule.every().day.at("09:00").do(send_review_reminders)

while True:
    schedule.run_pending()
    time.sleep(60)
```

## Lógica del Endpoint

1. Busca todas las órdenes con estado `'finalizado'`
2. Obtiene todos los `order_items` de estas órdenes
3. Filtra los items que no tienen reseña asociada
4. Para cada item sin reseña:
   - Verifica que hayan pasado más de 5 días desde la finalización
   - Usa `finalized_at` si está disponible, sino usa `created_at` como fallback
5. Agrupa los items por usuario
6. Envía un email a cada usuario con:
   - Lista de productos sin reseñar
   - Link directo a la página de reseñas: `{frontend_url}/reviews/{order_id}`

## Notas Importantes

- El endpoint **requiere autenticación** con `API_KEY` del `.env`. Debe enviarse en el header `X-API-Key` o `Authorization: Bearer <key>`.
- El endpoint calcula los días desde `finalized_at` (si existe) o `created_at` (fallback).
- Solo envía emails si han pasado **más de 5 días** desde la finalización.
- El `frontend_url` se obtiene de `Config.FRONTEND_URL` del `.env`.
