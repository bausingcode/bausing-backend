"""
API Pública - Formato Estándar de Respuestas

Todos los endpoints de esta API deben seguir el siguiente formato de respuesta:

================================================================================
MANEJO DE ERRORES
================================================================================

Códigos HTTP:
- 200: OK - Operación completada (éxito o error de negocio)
- 400: Bad Request - Error de validación de datos
- 401: Unauthorized - Token inválido o no proporcionado
- 500: Internal Server Error - Error del servidor

Estructura de Error:
Todos los errores retornan el mismo formato:
{
    "status": false,
    "message": "Descripción del error"
}

Tipos de Errores:

1. Error de Autenticación
   - HTTP Status: 401
   - Causa: Token inválido, expirado o no proporcionado
   - Ejemplo:
     {
         "status": false,
         "message": "Token inválido o no proporcionado"
     }

2. Error de Validación
   - HTTP Status: 200 (con status: false)
   - Causa: Datos enviados no cumplen con las validaciones
   - Ejemplo:
     {
         "status": false,
         "message": "Error de validación: El ID del vendedor es requerido"
     }

3. Error de Procesamiento
   - HTTP Status: 200 (con status: false)
   - Causa: Error interno al procesar la operación
   - Ejemplo:
     {
         "status": false,
         "message": "Error al procesar la operación: [descripción del error]"
     }

4. Error de Conexión/Servidor
   - HTTP Status: 500
   - Causa: Problemas de red o servidor no disponible
   - Ejemplo:
     {
         "status": false,
         "message": "Error interno del servidor"
     }

================================================================================
RESPONSE - ÉXITO
================================================================================

HTTP Status: 200 OK

Body:
{
    "status": true,
    "data": {
        // Datos de la respuesta
    },
    "message": "Operación completada exitosamente"
}

Ejemplo:
{
    "status": true,
    "data": {
        "venta_id": 123,
        "numero_comprobante": "0001-00001234"
    },
    "message": "Venta recibida correctamente"
}

================================================================================
USO DE FUNCIONES HELPER
================================================================================

Para mantener la consistencia, usar siempre las funciones helper:

- success_response(data, message) -> Respuesta de éxito (200)
- validation_error(message) -> Error de validación (200 con status: false)
- processing_error(message) -> Error de procesamiento (200 con status: false)
- authentication_error(message) -> Error de autenticación (401)
- server_error(message) -> Error del servidor (500)

Ejemplo de uso en un endpoint:

@public_api_bp.route('/endpoint', methods=['POST'])
@api_key_required
def mi_endpoint():
    try:
        # Validaciones
        if not request.json.get('campo'):
            return validation_error("El campo es requerido")
        
        # Procesamiento
        resultado = procesar_datos()
        
        return success_response(
            data={"id": resultado.id},
            message="Operación completada exitosamente"
        )
    except Exception as e:
        return server_error(f"Error del servidor: {str(e)}")
"""

from flask import Blueprint, request, jsonify
from functools import wraps
from config import Config
from database import db
from models.product import Product, ProductVariant, ProductPrice
from models.image import ProductImage
from models.category import Category
from models.test_table import TestTable
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import joinedload

public_api_bp = Blueprint('public_api', __name__)

# ============================================================================
# Funciones Helper para Respuestas Estandarizadas
# ============================================================================

def success_response(data=None, message="Operación completada exitosamente"):
    """
    Retorna una respuesta de éxito con formato estándar.
    
    HTTP Status: 200 OK
    
    Estructura:
    {
        "status": true,
        "data": {...},
        "message": "..."
    }
    """
    response = {
        "status": True,
        "message": message
    }
    if data is not None:
        response["data"] = data
    return jsonify(response), 200


def error_response(message, http_status=200):
    """
    Retorna una respuesta de error con formato estándar.
    
    HTTP Status: 
    - 200 para errores de validación/procesamiento
    - 401 para errores de autenticación
    - 500 para errores del servidor
    
    Estructura:
    {
        "status": false,
        "message": "..."
    }
    """
    return jsonify({
        "status": False,
        "message": message
    }), http_status


def validation_error(message):
    """
    Retorna un error de validación (HTTP 200 con status: false).
    """
    return error_response(f"Error de validación: {message}", 200)


def processing_error(message):
    """
    Retorna un error de procesamiento (HTTP 200 con status: false).
    """
    return error_response(f"Error al procesar la operación: {message}", 200)


def authentication_error(message="Token inválido o no proporcionado"):
    """
    Retorna un error de autenticación (HTTP 401).
    """
    return error_response(message, 401)


def server_error(message="Error interno del servidor"):
    """
    Retorna un error del servidor (HTTP 500).
    """
    return error_response(message, 500)


# ============================================================================
# Decorador de Autenticación
# ============================================================================

def api_key_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = None
        
        if 'X-API-Key' in request.headers:
            api_key = request.headers['X-API-Key']
        elif 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                api_key = auth_header.split(' ')[1]
            else:
                api_key = auth_header
        
        if not api_key:
            return authentication_error("Token inválido o no proporcionado")
        
        if api_key != Config.API_KEY:
            return authentication_error("Token inválido o no proporcionado")
        
        return f(*args, **kwargs)
    
    return decorated_function


# ============================================================================
# Endpoints
# ============================================================================

@public_api_bp.route('/public/health', methods=['GET'])
@api_key_required
def health_check():
    """
    Health check endpoint para verificar el estado de la API y la base de datos.
    
    Response - Éxito:
    HTTP Status: 200 OK
    {
        "status": true,
        "data": {
            "status": "healthy",
            "database": "connected" | "disconnected"
        },
        "message": "API funcionando correctamente"
    }
    
    Response - Error del Servidor:
    HTTP Status: 500 Internal Server Error
    {
        "status": false,
        "message": "Error interno del servidor"
    }
    """
    try:
        from sqlalchemy import text
        db.session.execute(text('SELECT 1'))
        db_status = 'connected'
    except Exception as e:
        db_status = 'disconnected'
        # Si hay un error crítico, retornar error 500
        return server_error(f"Error al conectar con la base de datos: {str(e)}")
    
    return success_response(
        data={
            "status": "healthy",
            "database": db_status
        },
        message="API funcionando correctamente"
    )


@public_api_bp.route('/public/sync-data-test', methods=['POST'])
@api_key_required
def sync_data():
    """
    Endpoint de prueba para recibir informes de cambios nuevos.
    Almacena la información recibida en la tabla test_table.
    
    Request Body:
    {
        // Cualquier estructura JSON
    }
    
    Response - Éxito:
    HTTP Status: 200 OK
    {
        "status": true,
        "data": {
            "id": 1,
            "created_at": "2024-01-01T00:00:00"
        },
        "message": "Datos sincronizados correctamente"
    }
    
    Response - Error de Validación:
    HTTP Status: 200 OK
    {
        "status": false,
        "message": "Error de validación: El body es requerido"
    }
    
    Response - Error de Procesamiento:
    HTTP Status: 200 OK
    {
        "status": false,
        "message": "Error al procesar la operación: [descripción del error]"
    }
    
    Response - Error del Servidor:
    HTTP Status: 500 Internal Server Error
    {
        "status": false,
        "message": "Error interno del servidor"
    }
    """
    try:
        # Validar que se recibió un body
        if not request.is_json:
            return validation_error("El body debe ser JSON")
        
        body_data = request.get_json()
        
        if body_data is None:
            return validation_error("El body es requerido")
        
        # Crear el registro en la base de datos
        try:
            test_record = TestTable(body=body_data)
            db.session.add(test_record)
            db.session.commit()
            
            return success_response(
                data={
                    "id": test_record.id,
                    "created_at": test_record.created_at.isoformat() if test_record.created_at else None
                },
                message="Datos sincronizados correctamente"
            )
        except Exception as e:
            db.session.rollback()
            return processing_error(f"No se pudo guardar los datos: {str(e)}")
            
    except Exception as e:
        return server_error(f"Error del servidor: {str(e)}")

