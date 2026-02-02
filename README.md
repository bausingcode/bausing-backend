# Bausing Backend

Backend Flask para la aplicación Bausing con gestión completa de catálogo.

## Características

✅ **Autenticación de Administradores**:
- Registro y login de usuarios admin
- Autenticación JWT
- Roles y permisos

✅ **Gestión de Catálogo Completo**:
- Categorías y Subcategorías (jerarquía completa)
- Productos con variantes
- Stock por variante
- Precios por localidad
- Gestión desde admin panel

✅ **Gestión de Imágenes**:
- Imágenes de productos (múltiples por producto)
- Hero images (banners principales)
- Almacenamiento en Supabase Storage
- URLs públicas automáticas

## Requisitos Previos

- Python 3.8+
- PostgreSQL 12+
- Base de datos `bausing` creada
- Usuario de PostgreSQL con permisos
- Cuenta de Supabase (para almacenamiento de imágenes)
- Buckets de Supabase creados: `product-images` y `hero-images`

## Instalación

1. Crear un entorno virtual:
```bash
python3 -m venv venv
```

2. Activar el entorno virtual:
```bash
# En macOS/Linux
source venv/bin/activate

# En Windows
venv\Scripts\activate
```

3. Instalar las dependencias:
```bash
pip install -r requirements.txt
```

4. Configurar variables de entorno:
   - Copia el archivo `.env.example` a `.env` (si existe) o crea uno nuevo
   - Configura las siguientes variables:
   ```env
   DATABASE_URL=postgresql://facu@localhost/bausing
   SECRET_KEY=tu-secret-key-segura
   SUPABASE_URL=https://tu-project-id.supabase.co
   SUPABASE_KEY=tu-service-role-key
   
   # MercadoPago (credenciales de prueba)
   MP_ACCESS_TOKEN=TEST-6103708889552760-020119-e487e24989b22c39d6d5f34743854b80-526482732
   MP_PUBLIC_KEY=TEST-851528f1-2389-49c8-8d2c-0d809b869bc0
   
   # URLs (ajustar según entorno)
   FRONTEND_URL=http://localhost:3000
   BACKEND_URL=http://localhost:5000
   ```

5. Configurar la base de datos:
   - Asegúrate de que PostgreSQL esté corriendo
   - Crea la base de datos: `createdb bausing`
   - La conexión se configura en el archivo `.env`

6. Inicializar las tablas:
```bash
python init_db.py
```

7. Crear roles de administrador iniciales:
```bash
python init_admin_roles.py
```

## Ejecución

Para ejecutar la aplicación:

```bash
python run.py
```

La aplicación estará disponible en `http://localhost:5000`

## Endpoints Principales

### Base
- `GET /` - Página principal con información de endpoints
- `GET /health` - Verificar estado del servidor y conexión a BD

### Autenticación Admin
- `POST /api/admin/auth/register` - Registrar nuevo usuario admin (requiere: email, password, role_id)
- `POST /api/admin/auth/login` - Login de usuario admin (requiere: email, password)
- `GET /api/admin/auth/me` - Obtener usuario actual (requiere token)
- `GET /api/admin/auth/roles` - Listar roles disponibles

### Categorías
- `GET /api/categories` - Obtener todas las categorías
- `GET /api/categories?parent_id=uuid` - Obtener subcategorías
- `GET /api/categories?include_children=true` - Obtener con subcategorías
- `POST /api/categories` - Crear categoría/subcategoría
- `PUT /api/categories/{id}` - Actualizar categoría
- `DELETE /api/categories/{id}` - Eliminar categoría

### Productos
- `GET /api/products` - Listar productos
- `GET /api/products/{id}` - Obtener producto
- `POST /api/products` - Crear producto básico
- `PUT /api/products/{id}` - Actualizar producto
- `DELETE /api/products/{id}` - Eliminar producto

### Imágenes de Productos
- `POST /api/products/{product_id}/images` - Subir imagen de producto (requiere token admin)
- `GET /api/products/{product_id}/images` - Obtener imágenes de un producto
- `PUT /api/products/images/{image_id}` - Actualizar imagen (alt_text, position) (requiere token admin)
- `DELETE /api/products/images/{image_id}` - Eliminar imagen (requiere token admin)

### Hero Images
- `POST /api/hero-images` - Subir hero image (requiere token admin)
- `GET /api/hero-images` - Listar hero images
- `GET /api/hero-images?active=true` - Listar solo hero images activas
- `GET /api/hero-images/{image_id}` - Obtener hero image específica
- `PUT /api/hero-images/{image_id}` - Actualizar hero image (requiere token admin)
- `DELETE /api/hero-images/{image_id}` - Eliminar hero image (requiere token admin)

### Admin Panel (Recomendado)
- `POST /api/admin/products/complete` - Crear producto completo (con variantes, stock y precios) (requiere token admin)
- `PUT /api/admin/products/{id}/complete` - Actualizar producto completo (requiere token admin)
- `GET /api/admin/categories/tree` - Árbol completo de categorías
- `GET /api/admin/catalog/summary` - Resumen del catálogo

### Variantes y Precios
- `GET /api/product-variants?product_id=uuid` - Variantes de un producto
- `POST /api/product-variants` - Crear variante
- `PATCH /api/product-variants/{id}/stock` - Actualizar stock
- `POST /api/product-prices` - Crear precio por localidad

### Localidades
- `GET /api/localities` - Listar localidades
- `POST /api/localities` - Crear localidad

**📖 Para más detalles, ver [ADMIN_API.md](ADMIN_API.md)**

## Estructura del Proyecto

```
bausing-backend/
├── app.py                  # Aplicación Flask principal
├── run.py                  # Script para ejecutar la aplicación
├── config.py               # Configuración de la aplicación
├── database.py             # Inicialización de SQLAlchemy
├── supabase_client.py      # Cliente de Supabase Storage
├── init_db.py              # Script para crear tablas
├── init_admin_roles.py     # Script para crear roles admin iniciales
├── requirements.txt        # Dependencias del proyecto
├── .env                    # Variables de entorno (no se sube a git)
├── models/                 # Modelos de base de datos
│   ├── __init__.py
│   ├── category.py
│   ├── product.py
│   ├── locality.py
│   ├── admin_user.py       # Modelos de usuarios admin
│   └── image.py            # Modelos de imágenes
├── routes/                 # Blueprints con endpoints
│   ├── __init__.py
│   ├── categories.py
│   ├── products.py
│   ├── product_variants.py
│   ├── product_prices.py
│   ├── localities.py
│   ├── admin.py            # Endpoints especiales para admin
│   ├── admin_auth.py       # Autenticación de administradores
│   └── images.py           # Gestión de imágenes
├── ADMIN_API.md           # Documentación detallada para admin panel
├── .gitignore            # Archivos a ignorar en git
└── README.md             # Este archivo
```

## Configuración

### Variables de Entorno

El proyecto usa un archivo `.env` para la configuración. Ejemplo:

```env
# Base de datos
DATABASE_URL=postgresql://usuario:password@localhost/bausing

# Flask
SECRET_KEY=tu-secret-key-muy-segura-aqui
SQLALCHEMY_ECHO=False

# Supabase (para almacenamiento de imágenes)
SUPABASE_URL=https://tu-project-id.supabase.co
SUPABASE_KEY=tu-service-role-key-de-supabase

# MercadoPago (para pagos con tarjeta)
# Credenciales de prueba:
MP_ACCESS_TOKEN=TEST-6103708889552760-020119-e487e24989b22c39d6d5f34743854b80-526482732
MP_PUBLIC_KEY=TEST-851528f1-2389-49c8-8d2c-0d809b869bc0

# URLs (ajustar según entorno)
FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:5000
```

**Importante**: 
- El archivo `.env` está en `.gitignore` y no se sube al repositorio
- Nunca compartas tus claves públicamente
- Usa una `SECRET_KEY` fuerte en producción

### Configuración de Supabase

1. Crea una cuenta en [Supabase](https://supabase.com)
2. Crea un nuevo proyecto
3. Ve a Storage y crea dos buckets públicos:
   - `product-images` (público)
   - `hero-images` (público)
4. Obtén tu `SUPABASE_URL` y `SUPABASE_KEY` (service_role key) desde la configuración del proyecto
5. Agrégalos al archivo `.env`

## Ejemplos de Uso

### 1. Autenticación Admin

```bash
# Login
curl -X POST http://localhost:5000/api/admin/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "password123"
  }'

# Respuesta incluye un token JWT que debes usar en headers:
# Authorization: Bearer <token>
```

### 2. Crear Producto Completo desde Admin Panel

```bash
curl -X POST http://localhost:5000/api/admin/products/complete \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "name": "Colchón Premium",
    "description": "Colchón de alta calidad",
    "sku": "COL-PREM-001",
    "subcategory_id": "uuid-colchones",
    "variants": [
      {
        "attributes": {
          "size": "Una plaza (80x190)",
          "combo": "Colchón + base"
        },
        "stock": 15,
        "prices": [
          {"locality_id": "uuid-localidad", "price": 89999.99}
        ]
      }
    ]
  }'
```

### 3. Subir Imagen de Producto

```bash
curl -X POST http://localhost:5000/api/products/{product_id}/images \
  -H "Authorization: Bearer <token>" \
  -F "file=@/path/to/image.jpg" \
  -F "alt_text=Imagen principal del producto" \
  -F "position=0"
```

### 4. Subir Hero Image

```bash
curl -X POST http://localhost:5000/api/hero-images \
  -H "Authorization: Bearer <token>" \
  -F "file=@/path/to/hero.jpg" \
  -F "title=Oferta Especial" \
  -F "subtitle=Descuentos hasta 50%" \
  -F "cta_text=Ver Ofertas" \
  -F "cta_link=/products?sale=true" \
  -F "position=0" \
  -F "is_active=true"
```

**📖 Ver más ejemplos en [ADMIN_API.md](ADMIN_API.md)**

# bausing-backend
