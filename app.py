from flask import Flask, jsonify, request
from config import Config
from database import db
from routes import register_routes
import os

app = Flask(__name__)
app.config.from_object(Config)

# Manejar CORS manualmente
@app.after_request
def after_request(response):
    """Agregar headers CORS a todas las respuestas"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.before_request
def handle_preflight():
    """Manejar requests OPTIONS (preflight de CORS)"""
    if request.method == "OPTIONS":
        response = jsonify({})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add('Access-Control-Allow-Headers', "Content-Type,Authorization")
        response.headers.add('Access-Control-Allow-Methods', "GET,PUT,POST,DELETE,OPTIONS")
        return response

# Forzar la lectura de DATABASE_URL desde .env (asegurar que se use el puerto correcto)
database_url = os.getenv('DATABASE_URL')
if database_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    # Verificar que esté usando el puerto 6543 (Transaction mode)
    if ':6543/' in database_url:
        print(f"✅ Usando Transaction mode (puerto 6543)")
    elif ':5432/' in database_url:
        print(f"⚠️  ADVERTENCIA: Aún usando Session mode (puerto 5432)")

# Configurar opciones del engine de SQLAlchemy
if hasattr(Config, 'SQLALCHEMY_ENGINE_OPTIONS'):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = Config.SQLALCHEMY_ENGINE_OPTIONS

# Inicializar base de datos
db.init_app(app)

# Asegurar que las sesiones se cierren después de cada request
@app.teardown_appcontext
def close_db(error):
    """Cerrar la sesión de la base de datos después de cada request"""
    db.session.remove()

# Registrar todas las rutas
register_routes(app)

@app.route('/')
def index():
    return jsonify({
        'message': 'Bienvenido a Bausing Backend',
        'status': 'ok',
        'endpoints': {
            'categorias': '/categories',
            'productos': '/products',
            'productos_busqueda': '/products?search=...&category_id=...&min_price=...&max_price=...',
            'producto_detalle': '/products/{id}',
            'productos_relacionados': '/products/{id}/related',
            'productos_destacados': '/products/featured',
            'sugerencias_busqueda': '/products/search-suggestions?q=...',
            'rango_precios': '/products/price-range',
            'variantes': '/product-variants',
            'precios': '/product-prices',
            'localidades': '/localities',
            'admin': '/admin',
            'admin_auth': '/admin/auth',
            'product_images': '/products/{id}/images',
            'hero_images': '/hero-images',
            'promos': '/promos',
            'auth_register': '/auth/register',
            'auth_login': '/auth/login',
            'auth_verify_email': '/auth/verify-email',
            'auth_resend_verification': '/auth/resend-verification',
            'auth_me': '/auth/me'
        }
    })

@app.route('/health')
def health():
    try:
        # Verificar conexión a la base de datos
        from sqlalchemy import text
        db.session.execute(text('SELECT 1'))
        db_status = 'connected'
    except:
        db_status = 'disconnected'
    
    return jsonify({
        'status': 'healthy',
        'database': db_status
    })

@app.route('/debug/db-config')
def debug_db_config():
    """Endpoint de debug para verificar la configuración de la base de datos"""
    database_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    # Ocultar la contraseña en la respuesta
    safe_url = database_url.split('@')[1] if '@' in database_url else database_url
    
    return jsonify({
        'database_url_host': safe_url,
        'port': '6543' if ':6543/' in database_url else ('5432' if ':5432/' in database_url else 'unknown'),
        'mode': 'Transaction' if ':6543/' in database_url else ('Session' if ':5432/' in database_url else 'unknown'),
        'pool_size': app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {}).get('pool_size', 'not set'),
        'max_overflow': app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {}).get('max_overflow', 'not set')
    })

if __name__ == '__main__':
    with app.app_context():
        # Crear tablas si no existen
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)

