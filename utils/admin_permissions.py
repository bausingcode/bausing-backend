from flask import request

# Nombres de blueprint (módulo de rutas) con acceso completo para cada rol
# restringido. Un rol que NO aparece acá tiene acceso completo a todo el panel
# (comportamiento histórico, sin restricciones) — así no se rompe a los admins
# existentes (Administrador, etc).
ROLE_ALLOWED_BLUEPRINTS = {
    'Editor de Contenido': {
        'products',      # Productos
        'categories',    # Categorías (parte de la gestión de Productos)
        'crm_products',  # Combos / completar productos (parte de Productos)
        'images',        # Imágenes
        'blog',          # Blog
        'faq_items',     # Preguntas Frecuentes
        'admin_auth',    # /admin/auth/me — necesario para cualquier sesión admin
    },
}

# Endpoints puntuales permitidos dentro de blueprints que mezclan varias
# secciones (ej. 'admin', que junto con /users y /customers también expone
# /auth/me).
ROLE_ALLOWED_ENDPOINTS = {
    'Editor de Contenido': {
        'admin.get_current_user',
    },
}


def check_admin_permission(admin_user):
    """
    Devuelve True si `admin_user` puede acceder al blueprint/endpoint de la
    request actual, según su rol.
    """
    role_name = admin_user.role.name if admin_user and admin_user.role else None
    allowed_blueprints = ROLE_ALLOWED_BLUEPRINTS.get(role_name)

    # Rol sin restricciones configuradas: acceso completo.
    if allowed_blueprints is None:
        return True

    if request.blueprint in allowed_blueprints:
        return True

    allowed_endpoints = ROLE_ALLOWED_ENDPOINTS.get(role_name, set())
    return request.endpoint in allowed_endpoints
