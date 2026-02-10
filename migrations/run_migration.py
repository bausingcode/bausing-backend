#!/usr/bin/env python3
"""
Script para ejecutar la migración de payment_method
Actualiza el tamaño de VARCHAR(50) a VARCHAR(200) en las tablas orders y sale_retry_queue
"""
import os
import sys
from sqlalchemy import text
from app import app
from database import db

def run_migration():
    """Ejecuta la migración SQL"""
    migration_sql = """
    -- Actualizar tabla orders
    ALTER TABLE orders 
    ALTER COLUMN payment_method TYPE VARCHAR(200);

    -- Actualizar tabla sale_retry_queue
    ALTER TABLE sale_retry_queue 
    ALTER COLUMN payment_method TYPE VARCHAR(200);
    """
    
    with app.app_context():
        try:
            print("🔄 Ejecutando migración: actualizar payment_method a VARCHAR(200)...")
            
            # Ejecutar la migración
            db.session.execute(text(migration_sql))
            db.session.commit()
            
            print("✅ Migración completada exitosamente")
            
            # Verificar los cambios
            verify_query = text("""
                SELECT 
                    table_name,
                    column_name,
                    data_type,
                    character_maximum_length
                FROM information_schema.columns
                WHERE table_name IN ('orders', 'sale_retry_queue')
                  AND column_name = 'payment_method'
                ORDER BY table_name;
            """)
            
            result = db.session.execute(verify_query)
            rows = result.fetchall()
            
            print("\n📊 Verificación de cambios:")
            print("-" * 60)
            for row in rows:
                table_name, column_name, data_type, max_length = row
                print(f"  {table_name}.{column_name}: {data_type}({max_length})")
            print("-" * 60)
            
            if all(row[3] == 200 for row in rows):
                print("\n✅ Todas las columnas fueron actualizadas correctamente a VARCHAR(200)")
            else:
                print("\n⚠️  Algunas columnas no fueron actualizadas correctamente")
                return 1
                
            return 0
            
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Error al ejecutar la migración: {str(e)}")
            import traceback
            traceback.print_exc()
            return 1

if __name__ == '__main__':
    exit_code = run_migration()
    sys.exit(exit_code)
