"""
Script para generar el slug de los productos que todavía no tienen uno
(productos creados antes de agregar la columna slug).
Requiere haber corrido antes sql/products_slug.sql.
Ejecutar: python backfill_product_slugs.py
"""
from app import app
from database import db
from models.product import Product, assign_unique_product_slug

with app.app_context():
    products = Product.query.filter(
        db.or_(Product.slug.is_(None), Product.slug == '')
    ).order_by(Product.created_at.asc()).all()

    print(f"Productos sin slug: {len(products)}")

    for product in products:
        assign_unique_product_slug(product, exclude_id=product.id)
        print(f"  {product.id} -> {product.slug}")

    db.session.commit()
    print("\n✅ Listo.")
