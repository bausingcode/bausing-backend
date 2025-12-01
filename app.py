from flask import Flask, jsonify
from config import Config
from database import db
from routes import register_routes

app = Flask(__name__)
app.config.from_object(Config)

# Inicializar base de datos
db.init_app(app)

# Registrar todas las rutas
register_routes(app)

@app.route('/')
def index():
    return jsonify({
        'message': 'Bienvenido a Bausing Backend',
        'status': 'ok',
        'endpoints': {
            'categorias': '/api/categories',
            'productos': '/api/products',
            'productos_busqueda': '/api/products?search=...&category_id=...&min_price=...&max_price=...',
            'producto_detalle': '/api/products/{id}',
            'productos_relacionados': '/api/products/{id}/related',
            'productos_destacados': '/api/products/featured',
            'sugerencias_busqueda': '/api/products/search-suggestions?q=...',
            'rango_precios': '/api/products/price-range',
            'variantes': '/api/product-variants',
            'precios': '/api/product-prices',
            'localidades': '/api/localities',
            'admin': '/api/admin',
            'admin_auth': '/api/admin/auth',
            'product_images': '/api/products/{id}/images',
            'hero_images': '/api/hero-images',
            'promos': '/api/promos'
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

if __name__ == '__main__':
    with app.app_context():
        # Crear tablas si no existen
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)

