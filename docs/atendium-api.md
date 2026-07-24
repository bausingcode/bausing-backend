# API Atendium — Bausing

Documentación de la API tool-oriented para integrar el bot de Atendium con Bausing.

**Base URL:** `{BACKEND_URL}/atendium/v1`  
Ejemplo local: `http://localhost:5000/atendium/v1`

**Auth (requerida en todos los endpoints):**

```
X-API-Key: <API_KEY>
```

También acepta `Authorization: Bearer <misma_clave>`.

Variable de entorno: `API_KEY`.

**Formato de respuesta:**

```json
{ "status": true, "message": "...", "data": { } }
```

Error:

```json
{ "status": false, "message": "..." }
```

---

## Endpoints

### `GET /health`

Verifica API + DB.

---

### `POST /resolve-zone`

Resuelve localidad, catálogo, zona CRM, flags de envío y días estimados a partir de una dirección.

**Body (coords o dirección):**

```json
{
  "street": "San Martín",
  "number": "100",
  "city": "Córdoba",
  "province": "Córdoba",
  "postal_code": "5000",
  "lat": -31.4201,
  "lon": -64.1888
}
```

Si hay `lat`/`lon`, no hace falta geocodificar. Si no, se geocodifica con street+city.

**`data` típico:**

| Campo | Descripción |
|-------|-------------|
| `locality.id` / `locality.name` | Localidad Bausing |
| `catalog_id` | Catálogo de precios de esa localidad |
| `crm_zone_id` | Zona CRM |
| `is_pais_catalog` | `true` → Catálogo País (handoff) |
| `is_third_party_transport` | Transporte tercerizado |
| `shipping_price` | Precio fijo si tercerizado |
| `estimated_delivery` | `{ min_days, max_days, label }` |

---

### `GET /catalog`

Busca productos activos con precios según localidad.

**Query:**

| Param | Descripción |
|-------|-------------|
| `q` | Texto de búsqueda |
| `locality_id` | UUID localidad (precios + días) |
| `category_id` | Filtro categoría |
| `page` | Default 1 |
| `per_page` | Default 20, max 50 |

**Cada producto:** `id`, `name`, `description`, `main_image`, `price_transfer`, `price_card`, `promos`, más `estimated_delivery` a nivel respuesta.

---

### `GET /catalog/<product_id>`

Detalle de un producto. Query: `locality_id` (recomendado).

---

### `POST /validate-coupon`

Valida un cupón y calcula descuento (sin reservarlo).

```json
{
  "coupon_code": "VERANO10",
  "items": [
    { "product_id": "<uuid>", "quantity": 1, "price": 50000 }
  ]
}
```

`price` es unitario. Si falla → `status: false` + mensaje.

---

### `POST /validate-referral`

```json
{
  "referral_code": "ABC123",
  "customer_email": "opcional@mail.com"
}
```

El referido **no baja el total** al instante (crédito al referidor al finalizar, igual que web).  
`customer_email` sirve para bloquear auto-referido.

---

### `POST /quote`

Cotización completa: precios por zona, cupón, envío, días, y si se puede cerrar o hay que derivar a persona.

```json
{
  "address": {
    "street": "San Martín",
    "number": "100",
    "city": "Córdoba",
    "province": "Córdoba",
    "postal_code": "5000",
    "lat": -31.4201,
    "lon": -64.1888
  },
  "items": [{ "product_id": "<uuid>", "quantity": 1 }],
  "payment_method": "transfer",
  "coupon_code": "VERANO10",
  "referral_code": "ABC123",
  "customer": { "email": "opcional@mail.com" }
}
```

`payment_method`: `cash` | `transfer` | `card`.

**`data` importante:**

| Campo | Descripción |
|-------|-------------|
| `items[]` | Líneas con `unit_price`, `line_total` |
| `subtotal` | Suma productos |
| `coupon_discount` | Descuento cupón |
| `subtotal_after_coupon` | Subtotal − cupón |
| `shipping_cost` / `shipping_kind` | `third_party` \| `viacargo` \| `accessories` \| `none` |
| `total` | A cobrar |
| `estimated_delivery` | Días del catálogo |
| `can_create_order` | `true` → se puede `POST /orders` |
| `requires_human_handoff` | `true` → derivar a persona |
| `handoff_reason` | `pais_catalog` \| `third_party_card` \| `third_party_transfer` |
| `handoff_message` | Texto para el bot |
| `whatsapp_phone` | Teléfono de settings (si aplica) |

**Envío (misma lógica que checkout web):**

1. Tercerizado → `shipping_price` de zona  
2. Catálogo País → cotización Vía Cargo (requiere CP)  
3. Zona local + carrito 100% “Almohadas y accesorios” → `catalog.accessories_shipping_price`  
4. Si no → `0`

Cupón o referido inválidos → error (hard-fail).

---

### `POST /orders`

Crea la venta en CRM (pago contra entrega) **solo si** el quote permitiría cerrarla.

```json
{
  "customer": {
    "first_name": "Juan",
    "last_name": "Pérez",
    "email": "juan@mail.com",
    "phone": "3515551234",
    "dni": "30111222",
    "document_type": "DNI"
  },
  "address": {
    "street": "San Martín",
    "number": "100",
    "city": "Córdoba",
    "province": "Córdoba",
    "province_id": "<uuid-opcional-si-mandás-province>",
    "postal_code": "5000",
    "lat": -31.4201,
    "lon": -64.1888
  },
  "items": [{ "product_id": "<uuid>", "quantity": 1 }],
  "payment_method": "cash",
  "total": 255000,
  "coupon_code": null,
  "referral_code": null,
  "observations": "opcional"
}
```

- Find-or-create usuario por email.  
- Recalcula quote server-side; si mandás `total`, debe coincidir (±1 ARS).  
- `province_id` o `province` (nombre) requerido.  
- Observaciones quedan con origen `Atendium bot`.

**Si requiere handoff → HTTP 409:**

```json
{
  "status": false,
  "message": "Esta zona usa Catálogo País: la venta debe completarla un asesor.",
  "data": {
    "can_create_order": false,
    "requires_human_handoff": true,
    "handoff_reason": "pais_catalog",
    "handoff_message": "...",
    "whatsapp_phone": "+54...",
    "quote_summary": { }
  }
}
```

**Matriz cierre vs handoff (paridad checkout):**

| Condición | Resultado |
|-----------|-----------|
| Catálogo País (cualquier pago) | Handoff → persona |
| Tercerizado + `card` | Handoff |
| Tercerizado + `transfer` | Handoff |
| Zona local + `cash` / `transfer` / `card` (COD) | Crea orden CRM |

---

### `GET /orders?phone=` o `?dni=`

Lista pedidos recientes del cliente.

Query: `phone` y/o `dni`, `limit` (default 10, max 50).

---

### `GET /orders/<id>?phone=`

Estado de un pedido. `<id>` = UUID de `orders` o `crm_order_id` numérico.  
`phone` obligatorio (valida que el pedido sea de ese cliente).

Incluye `status`, `crm_order_id`, `estimated_delivery`, items, etc.

---

## Flujo sugerido para el bot

1. Pedir dirección → `POST /resolve-zone` (mostrar días estimados).  
2. Buscar productos → `GET /catalog?q=...&locality_id=...`.  
3. Armar carrito → `POST /quote` (con `payment_method`, cupón/referido si los menciona).  
4. Si `requires_human_handoff` → derivar a persona (usar `handoff_message` + `whatsapp_phone`).  
5. Si `can_create_order` → confirmar datos → `POST /orders`.  
6. Seguimiento → `GET /orders/<crm_order_id>?phone=...`.

---

## Notas

- Código: `bausing-backend/routes/atendium.py` + `services/atendium_commerce.py`.  
- No usa wallet ni MercadoPago online en v1.  
- Precios dependen de la localidad (catálogo). Sin `locality_id` / zona, los precios pueden no coincidir con checkout.  
- Cupón y referido usan la misma lógica que el checkout web.
