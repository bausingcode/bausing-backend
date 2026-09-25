"""
Script para poner el alt de las imágenes de producto = nombre del producto
(reemplaza los alts viejos, que quedaron con el nombre del archivo subido).
Ejecutar: python backfill_product_image_alts.py
"""
from app import app
from database import db
from sqlalchemy import text

with app.app_context():
    result = db.session.execute(
        text(
            """
            UPDATE product_images pi
            SET alt_text = p.name
            FROM products p
            WHERE pi.product_id = p.id
            """
        )
    )
    db.session.commit()
    print(f"✅ {result.rowcount} imágenes actualizadas.")
