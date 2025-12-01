"""
Script para inicializar roles de administrador básicos.
Ejecutar: python init_admin_roles.py
"""
from app import app
from database import db
from models.admin_user import AdminRole

with app.app_context():
    print("Inicializando roles de administrador...")
    
    # Crear roles básicos si no existen
    roles_to_create = [
        {'name': 'Super Admin'},
        {'name': 'Administrator'},
        {'name': 'Editor'},
        {'name': 'Viewer'}
    ]
    
    created_count = 0
    for role_data in roles_to_create:
        existing_role = AdminRole.query.filter_by(name=role_data['name']).first()
        if not existing_role:
            role = AdminRole(name=role_data['name'])
            db.session.add(role)
            created_count += 1
            print(f"  ✅ Creado rol: {role_data['name']}")
        else:
            print(f"  ⏭️  Rol ya existe: {role_data['name']}")
    
    if created_count > 0:
        db.session.commit()
        print(f"\n✅ {created_count} rol(es) creado(s) exitosamente!")
    else:
        print("\n✅ Todos los roles ya existen.")
    
    # Mostrar todos los roles disponibles
    print("\nRoles disponibles:")
    all_roles = AdminRole.query.all()
    for role in all_roles:
        print(f"  - {role.name} (ID: {role.id})")


