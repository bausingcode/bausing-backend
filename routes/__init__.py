from flask import Blueprint

def register_routes(app):
    from .categories import categories_bp
    from .products import products_bp
    from .product_variants import variants_bp
    from .product_prices import prices_bp
    from .localities import localities_bp
    from .admin import admin_bp
    from .admin_auth import admin_auth_bp
    from .images import images_bp
    from .promos import promos_bp

    app.register_blueprint(categories_bp, url_prefix='/api/categories')
    app.register_blueprint(products_bp, url_prefix='/api/products')
    app.register_blueprint(variants_bp, url_prefix='/api/product-variants')
    app.register_blueprint(prices_bp, url_prefix='/api/product-prices')
    app.register_blueprint(localities_bp, url_prefix='/api/localities')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(admin_auth_bp, url_prefix='/api/admin/auth')
    app.register_blueprint(images_bp, url_prefix='/api')
    app.register_blueprint(promos_bp, url_prefix='/api/promos')

