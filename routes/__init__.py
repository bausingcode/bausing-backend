from flask import Blueprint

def register_routes(app):
    from .categories import categories_bp
    from .products import products_bp
    from .product_variants import variants_bp
    from .product_prices import prices_bp
    from .localities import localities_bp
    from .admin import admin_bp
    from .admin_auth import admin_auth_bp
    from .admin_stats import admin_stats_bp
    from .images import images_bp
    from .promos import promos_bp
    from .settings import settings_bp, public_settings_bp
    from .auth import auth_bp
    from .blog import blog_bp
    from .wallet import wallet_bp
    from .public_api import public_api_bp
    from .crm_products import crm_products_bp
    from .orders import orders_bp
    from .homepage_distribution import homepage_distribution_bp
    from .locality_detection import locality_detection_bp
    from .catalogs import catalogs_bp
    from .carts import carts_bp

    app.register_blueprint(categories_bp, url_prefix='/categories')
    app.register_blueprint(products_bp, url_prefix='/products')
    app.register_blueprint(variants_bp, url_prefix='/product-variants')
    app.register_blueprint(prices_bp, url_prefix='/product-prices')
    app.register_blueprint(localities_bp, url_prefix='/localities')
    app.register_blueprint(catalogs_bp, url_prefix='/catalogs')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(admin_auth_bp, url_prefix='/admin/auth')
    app.register_blueprint(admin_stats_bp, url_prefix='/admin')
    app.register_blueprint(images_bp, url_prefix='')
    app.register_blueprint(promos_bp, url_prefix='/promos')
    app.register_blueprint(settings_bp, url_prefix='/admin')
    app.register_blueprint(public_settings_bp, url_prefix='')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(blog_bp, url_prefix='/blog')
    app.register_blueprint(wallet_bp, url_prefix='')
    app.register_blueprint(public_api_bp, url_prefix='')
    app.register_blueprint(crm_products_bp, url_prefix='')
    app.register_blueprint(orders_bp, url_prefix='/api')
    app.register_blueprint(homepage_distribution_bp, url_prefix='')
    app.register_blueprint(locality_detection_bp, url_prefix='/')
    app.register_blueprint(carts_bp, url_prefix='/carts')

