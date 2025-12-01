"""
Script para inicializar la base de datos y crear las tablas.
Ejecutar: python init_db.py
"""
from app import app
from database import db

with app.app_context():
    print("Creando tablas en la base de datos...")
    db.create_all()
    print("✅ Tablas creadas exitosamente!")
    print("\nPuedes ahora ejecutar el servidor con: python run.py")

