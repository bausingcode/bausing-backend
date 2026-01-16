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
import json
import uuid
import requests

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


@public_api_bp.route('/public/sincronizar-test', methods=['POST'])
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


@public_api_bp.route('/public/sincronizar', methods=['POST'])
@api_key_required
def sync_data_new():
    """
    Endpoint para sincronizar datos desde CRM.
    
    - Si tipo es "productos": usa la función crm_sync_products
    - Si tipo es "zonas": usa la función crm_sync_zones
    - Si tipo es "provincias": usa la función sync_crm_provincias
    - Si tipo es "tipos_documento": usa la función sync_crm_tipos_documento
    - Si tipo es "tipos_venta": usa la función sync_crm_tipos_venta
    - Si tipo es "ventas": usa la función sync_crm_ventas (detecta cambios de estado)
    - Si tipo es "medios_pago": omite la sincronización (simulado)
    
    Request Body:
    {
        "tipo": "productos" | "zonas" | "provincias" | "tipos_documento" | "tipos_venta" | "ventas" | "medios_pago",
        "datos": [...],
        "status": true,
        "filtros": {...},
        "sincronizar": {
            "accion": "update" | "create",
            "timestamp": "2026-01-02 13:33:31"
        }
    }
    
    Response - Éxito:
    HTTP Status: 200 OK
    {
        "status": true,
        "data": {},
        "message": "Datos sincronizados correctamente"
    }
    
    Response - Error de Validación:
    HTTP Status: 200 OK
    {
        "status": false,
        "message": "Error de validación: [descripción]"
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
        
        # Validar estructura básica
        if 'tipo' not in body_data:
            return validation_error("El campo 'tipo' es requerido")
        
        if 'datos' not in body_data:
            return validation_error("El campo 'datos' es requerido")
        
        if 'sincronizar' not in body_data:
            return validation_error("El campo 'sincronizar' es requerido")
        
        tipo = body_data.get('tipo')
        
        # Tipos que se simulan (no se procesan realmente)
        tipos_simulados = ['medios_pago']
        
        # Si es un tipo simulado, hacer pass (no procesar)
        if tipo in tipos_simulados:
            return success_response(
                data={},
                message=f"Sincronización de {tipo} exitosa"
            )
        
        # Determinar qué función usar según el tipo
        if tipo == 'productos':
            function_name = 'crm_sync_products'
        elif tipo == 'zonas':
            function_name = 'crm_sync_zones'
        elif tipo == 'provincias':
            function_name = 'sync_crm_provincias'
        elif tipo == 'tipos_documento':
            function_name = 'sync_crm_tipos_documento'
        elif tipo == 'tipos_venta':
            function_name = 'sync_crm_tipos_venta'
        elif tipo == 'ventas':
            function_name = 'sync_crm_ventas'
        else:
            return validation_error(f"Tipo '{tipo}' no soportado. Tipos válidos: productos, zonas, provincias, tipos_documento, tipos_venta, ventas, medios_pago")
        
        # Llamar a la función correspondiente
        try:
            from sqlalchemy import text, bindparam
            from sqlalchemy.dialects.postgresql import JSONB
            
            # Para ventas, necesitamos obtener estados anteriores ANTES de sincronizar
            # Hacerlo en una transacción separada para evitar conflictos
            estados_anteriores = {}
            if tipo == 'ventas':
                try:
                    # Asegurarse de que no hay transacción abortada antes de consultar
                    try:
                        db.session.rollback()
                    except:
                        pass
                    estados_anteriores = obtener_estados_anteriores_ventas(body_data.get('datos', []))
                    # Hacer rollback después de leer para limpiar la transacción
                    try:
                        db.session.rollback()
                    except:
                        pass
                except Exception as e:
                    # Si falla obtener estados anteriores, hacer rollback y continuar sin ellos
                    try:
                        db.session.rollback()
                    except:
                        pass
                    print(f"Advertencia: No se pudieron obtener estados anteriores: {str(e)}")
                    estados_anteriores = {}
            
            # Llamar a la función usando bindparam con tipo JSONB
            # SQLAlchemy JSONB acepta dict directamente o string JSON
            if tipo == 'ventas':
                # sync_crm_ventas retorna resultados, usar SELECT * FROM
                result = db.session.execute(
                    text(f"SELECT * FROM {function_name}(:json_data)").bindparams(
                        bindparam('json_data', type_=JSONB)
                    ),
                    {"json_data": body_data}
                )
                
                # Procesar resultados y detectar cambios de estado
                rows = result.fetchall()
                for row in rows:
                    crm_order_id = row[0]  # p_crm_order_id
                    nuevo_estado = row[1]   # delivery_status
                    accion = row[2]         # affected
                    
                    # Obtener estado anterior
                    estado_anterior = estados_anteriores.get(crm_order_id)
                    
                    # Si el estado cambió, hacer print
                    if estado_anterior and estado_anterior != nuevo_estado:
                        print(f"⚠️ CAMBIO DE ESTADO - Venta ID: {crm_order_id}")
                        print(f"   Estado anterior: {estado_anterior}")
                        print(f"   Estado nuevo: {nuevo_estado}")
                        print(f"   Acción: {accion}")
            else:
                # Otras funciones retornan void o un valor simple
                result = db.session.execute(
                    text(f"SELECT {function_name}(:json_data)").bindparams(
                        bindparam('json_data', type_=JSONB)
                    ),
                    {"json_data": body_data}
                )
            
            db.session.commit()
            
            return success_response(
                data={},
                message="Datos sincronizados correctamente"
            )
            
        except Exception as e:
            db.session.rollback()
            return processing_error(f"Error al sincronizar datos: {str(e)}")
            
    except Exception as e:
        return server_error(f"Error del servidor: {str(e)}")


def obtener_estados_anteriores_ventas(datos_ventas):
    """
    Obtiene los estados actuales de las ventas antes de sincronizar.
    Retorna un diccionario con crm_order_id -> estado_actual
    Usa una transacción separada para no interferir con la sincronización.
    """
    if not datos_ventas:
        return {}
    
    from sqlalchemy import text
    
    # Extraer los IDs de las ventas del payload
    venta_ids = []
    for venta in datos_ventas:
        if isinstance(venta, dict) and 'id' in venta:
            venta_ids.append(venta['id'])
    
    if not venta_ids:
        return {}
    
    # Query para obtener estados actuales
    # Usar IN con placeholders dinámicos (más compatible con SQLAlchemy)
    if len(venta_ids) == 0:
        return {}
    
    # Crear placeholders para cada ID
    placeholders = ','.join([f':id{i}' for i in range(len(venta_ids))])
    query = f"""
        SELECT crm_order_id, status
        FROM crm_orders
        WHERE crm_order_id IN ({placeholders})
    """
    
    # Usar una transacción separada para no interferir con la sincronización
    try:
        # Crear parámetros con los IDs
        params = {f'id{i}': venta_id for i, venta_id in enumerate(venta_ids)}
        
        # Ejecutar en una transacción separada
        result = db.session.execute(
            text(query),
            params
        )
        rows = result.fetchall()
        
        # Construir diccionario id -> estado
        estados = {}
        for row in rows:
            estados[row[0]] = row[1]
        
        # No hacer commit aquí, solo leer datos
        return estados
    except Exception as e:
        # Si hay error, hacer rollback y retornar diccionario vacío (no crítico)
        try:
            db.session.rollback()
        except:
            pass
        print(f"Error al obtener estados anteriores: {str(e)}")
        return {}


# SELECT pg_get_functiondef('crm_sync_products(jsonb)'::regprocedure);
# SELECT crm_sync_zones('{"tipo":"zonas","datos":[...],"sincronizar":{"accion":"update","timestamp":"2026-01-02 12:46:16"}}'::jsonb);
# -- Ejemplo de uso:
# -- SELECT sync_crm_provincias('{
# --   "tipo":"provincias",
# --   "status":true,
# --   "filtros":{},
# --   "datos":[{"id":1,"provincia":"Buenos Aires","orden":1,"created_at":"2024-01-01 10:00:00","updated_at":"2024-01-15 10:30:00"}],
# --   "sincronizar":{"accion":"update","timestamp":"2026-01-02 12:46:16"}
# -- }'::jsonb);
# -- EJEMPLO DE USO:
# -- SELECT * FROM sync_crm_tipos_documento(
# --   '{
# --     "tipo":"tipos_documento",
# --     "datos":[{"id":1,"tipo":"DNI","numero":1,"created_at":"2024-01-01 10:00:00","updated_at":"2024-01-15 10:30:00"}],
# --     "status":true,
# --     "filtros":{},
# --     "sincronizar":{"accion":"update","timestamp":"2026-01-02 12:46:16"}
# --   }'::jsonb
# -- );
# -- Ejemplo de uso sync_crm_ventas (pegás el JSON completo como jsonb):
# -- SELECT * FROM sync_crm_ventas('{ EJEMPLO }'::jsonb);
# -- La función retorna 3 columnas:
# -- p_crm_order_id (int), delivery_status (text) ← viene de datos[].estado, affected (text) ← viene de sincronizar.accion


@public_api_bp.route('/api/ventas/lista', methods=['POST'])
@api_key_required
def listar_ventas():
    """
    Endpoint para LISTAR ventas del CRM.
    
    Devuelve todas las ventas del CRM (o filtradas por id o fecha si se proporcionan).
    Las ventas se filtran por vendedor_id según el api_secret del token.
    
    Request Body (opcional):
    {
        "id": 12345 (opcional),
        "fecha": "2024-01-15 10:30:00" (opcional)
    }
    
    Response - Éxito:
    HTTP Status: 200 OK
    {
        "status": true,
        "tipo": "ventas",
        "filtros": {},
        "datos": [...],
        "sincronizar": {
            "accion": "sincronizar",
            "timestamp": "2024-01-15 10:30:00"
        }
    }
    
    Response - Error 404:
    HTTP Status: 404 Not Found
    {
        "status": false,
        "message": "El ID 999 no existe para el tipo ventas",
        "tipo": "ventas",
        "filtros": {"id": 999},
        "datos": []
    }
    """
    try:
        # Obtener datos del body si existe (opcional)
        data = request.get_json() or {}
        
        registro_id = data.get('id')
        fecha = data.get('fecha')
        search = data.get('search', '').strip()
        estados = data.get('estados', [])
        medios_pago = data.get('medios_pago', [])
        fecha_desde = data.get('fecha_desde')
        fecha_hasta = data.get('fecha_hasta')
        page = data.get('page', 1)
        per_page = data.get('per_page', 10)
        
        # Obtener api_secret del token
        api_key = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                api_key = auth_header.split(' ')[1]
        
        # TODO: Obtener vendedor_id desde api_secret
        # Por ahora, se devuelven todas las ventas
        # En el futuro, filtrar por: WHERE co.crm_seller_id = :vendedor_id
        vendedor_id = None  # Se obtendrá de una tabla de mapeo api_secret -> vendedor_id
        
        # Construir filtros para la respuesta
        filtros = {}
        if registro_id:
            filtros['id'] = registro_id
        elif fecha:
            filtros['fecha'] = fecha
        if search:
            filtros['search'] = search
        if estados:
            filtros['estados'] = estados
        if medios_pago:
            filtros['medios_pago'] = medios_pago
        if fecha_desde:
            filtros['fecha_desde'] = fecha_desde
        if fecha_hasta:
            filtros['fecha_hasta'] = fecha_hasta
        
        # Obtener ventas del CRM
        try:
            result = obtener_ventas_crm(
                registro_id=registro_id,
                fecha=fecha,
                vendedor_id=vendedor_id,
                search=search,
                estados=estados,
                medios_pago=medios_pago,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                page=page,
                per_page=per_page
            )
            ventas = result['ventas']
            total = result['total']
        except Exception as e:
            import traceback
            return jsonify({
                "status": False,
                "message": "Error al procesar la sincronización",
                "error": str(e) if Config.DEBUG_MODE else None,
                "traceback": traceback.format_exc() if Config.DEBUG_MODE else None
            }), 500
        
        # Si se solicitó un ID específico y no se encontró
        if registro_id and len(ventas) == 0:
            return jsonify({
                "status": False,
                "message": f"El ID {registro_id} no existe para el tipo ventas",
                "tipo": "ventas",
                "filtros": filtros,
                "datos": []
            }), 404
        
        # Generar timestamp
        from datetime import datetime
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        return jsonify({
            "status": True,
            "tipo": "ventas",
            "filtros": filtros,
            "datos": ventas,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page if per_page > 0 else 0
            },
            "sincronizar": {
                "accion": "sincronizar",
                "timestamp": timestamp
            }
        }), 200
        
    except Exception as e:
        import traceback
        return jsonify({
            "status": False,
            "message": "Error al procesar la sincronización",
            "error": str(e) if Config.DEBUG_MODE else None,
            "traceback": traceback.format_exc() if Config.DEBUG_MODE else None
        }), 500


def obtener_ventas_crm(registro_id=None, fecha=None, vendedor_id=None, search=None, estados=None, medios_pago=None, fecha_desde=None, fecha_hasta=None, page=1, per_page=10):
    """
    Obtiene ventas del CRM desde la tabla crm_orders con sus renglones y pagos.
    """
    from sqlalchemy import text
    
    # Query base para obtener encabezados de ventas
    query_base = """
        SELECT 
            co.crm_order_id as id,
            co.receipt_number as numero_comprobante,
            co.detail_date as fecha_detalle,
            co.crm_seller_id as vendedor_id,
            co.client_name as cliente_nombre,
            co.client_address as cliente_direccion,
            co.client_phone as cliente_telefono,
            co.client_email as email_cliente,
            co.client_document as documento_cliente,
            co.crm_doc_type_id as tipo_documento_cliente,
            co.crm_province_id as provincia_id,
            co.city as localidad,
            co.crm_zone_id as zona_id,
            co.crm_sale_type_id as tipo_venta,
            co.status as estado,
            co.total_sale as total_venta,
            co.total_with_payment as total_con_fpago,
            CASE WHEN co.is_cancelled THEN 1 ELSE 0 END as venta_cancelada,
            co.delivery_date as fecha_entrega,
            co.cobranza_at as fecha_paso_cobranza,
            co.caja_at as fecha_paso_caja,
            co.crm_created_at as created_at,
            co.crm_updated_at as updated_at
        FROM crm_orders co
        WHERE 1=1
    """
    
    params = {}
    conditions = []
    
    if registro_id:
        conditions.append("co.crm_order_id = :id")
        params['id'] = registro_id
    elif fecha:
        conditions.append("co.crm_updated_at >= :fecha::timestamp")
        params['fecha'] = fecha
    
    # Filtrar por vendedor si se proporciona
    if vendedor_id:
        conditions.append("co.crm_seller_id = :vendedor_id")
        params['vendedor_id'] = vendedor_id
    
    # Filtro de búsqueda
    if search:
        conditions.append("""
            (co.receipt_number ILIKE :search OR 
             co.client_name ILIKE :search OR 
             co.crm_order_id::text ILIKE :search)
        """)
        params['search'] = f'%{search}%'
    
    # Filtro por estados
    if estados and len(estados) > 0:
        placeholders = ','.join([f':estado_{i}' for i in range(len(estados))])
        conditions.append(f"co.status IN ({placeholders})")
        for i, estado in enumerate(estados):
            params[f'estado_{i}'] = estado
    
    # Filtro por fecha desde
    if fecha_desde:
        conditions.append("co.detail_date >= :fecha_desde::date")
        params['fecha_desde'] = fecha_desde
    
    # Filtro por fecha hasta
    if fecha_hasta:
        conditions.append("co.detail_date <= :fecha_hasta::date")
        params['fecha_hasta'] = fecha_hasta
    
    # Filtro por medios de pago (requiere JOIN con pagos procesados)
    join_pagos = ""
    if medios_pago and len(medios_pago) > 0:
        join_pagos = """
            INNER JOIN crm_order_payments_processed copp ON co.crm_order_id = copp.crm_order_id
        """
        placeholders = ','.join([f':medio_{i}' for i in range(len(medios_pago))])
        conditions.append(f"copp.payment_method_description IN ({placeholders})")
        for i, medio in enumerate(medios_pago):
            params[f'medio_{i}'] = medio
    
    # Construir query con condiciones
    where_clause = ""
    if conditions:
        where_clause = " AND " + " AND ".join(conditions)
    
    # Query para contar total (sin paginación)
    count_query = f"""
        SELECT COUNT(DISTINCT co.crm_order_id) as total
        FROM crm_orders co
        {join_pagos}
        WHERE 1=1 {where_clause}
    """
    
    # Query principal con paginación
    query = query_base + join_pagos + where_clause + " ORDER BY co.crm_order_id DESC"
    
    # Aplicar paginación
    offset = (page - 1) * per_page
    query += f" LIMIT :per_page OFFSET :offset"
    params['per_page'] = per_page
    params['offset'] = offset
    
    try:
        # Obtener total
        count_result = db.session.execute(text(count_query), params)
        total = count_result.scalar() or 0
        
        # Obtener ventas paginadas
        result = db.session.execute(text(query), params)
        rows = result.fetchall()
    except Exception as e:
        import traceback
        raise
    
    ventas = []
    
    for row in rows:
        try:
            venta_id = row.id
            
            # Obtener renglones (js) con sus formaPagos
            renglones = obtener_renglones_venta(venta_id)
            
            # Obtener pagos procesados
            pagos_procesados = obtener_pagos_procesados_venta(venta_id)
            
            venta = {
                'id': venta_id,
                'numero_comprobante': row.numero_comprobante,
                'fecha_detalle': row.fecha_detalle.strftime('%Y-%m-%d') if row.fecha_detalle else None,
                'vendedor_id': row.vendedor_id,
                'cliente_nombre': row.cliente_nombre,
                'cliente_direccion': row.cliente_direccion,
                'cliente_telefono': row.cliente_telefono,
                'email_cliente': row.email_cliente,
                'documento_cliente': row.documento_cliente,
                'tipo_documento_cliente': row.tipo_documento_cliente,
                'provincia_id': row.provincia_id,
                'localidad': row.localidad,
                'zona_id': row.zona_id,
                'tipo_venta': row.tipo_venta,
                'estado': row.estado,
                'total_venta': float(row.total_venta) if row.total_venta else 0.0,
                'total_con_fpago': float(row.total_con_fpago) if row.total_con_fpago else 0.0,
                'venta_cancelada': row.venta_cancelada,
                'fecha_entrega': row.fecha_entrega.strftime('%Y-%m-%d %H:%M:%S') if row.fecha_entrega else None,
                'fecha_paso_cobranza': row.fecha_paso_cobranza.strftime('%Y-%m-%d %H:%M:%S') if hasattr(row, 'fecha_paso_cobranza') and row.fecha_paso_cobranza else None,
                'fecha_paso_caja': row.fecha_paso_caja.strftime('%Y-%m-%d %H:%M:%S') if hasattr(row, 'fecha_paso_caja') and row.fecha_paso_caja else None,
                'js': renglones,
                'pagos_procesados': pagos_procesados,
                'created_at': row.created_at.strftime('%Y-%m-%d %H:%M:%S') if row.created_at else None,
                'updated_at': row.updated_at.strftime('%Y-%m-%d %H:%M:%S') if row.updated_at else None
            }
            ventas.append(venta)
        except Exception as e:
            # Continuar con la siguiente venta en lugar de fallar completamente
            continue
    
    return {
        'ventas': ventas,
        'total': total
    }


def obtener_renglones_venta(crm_order_id):
    """
    Obtiene los renglones (items) de una venta con sus propuestas de pago.
    """
    from sqlalchemy import text
    
    query = """
        SELECT 
            coi.id,
            coi.crm_row_id as encabezado_detalle_recibir_id,
            coi.item_id,
            coi.quantity as cantidad_recibida,
            coi.price as precio,
            coi.cost_price as precio_costo,
            coi.commission as comision
        FROM crm_order_items coi
        WHERE coi.crm_order_id = :crm_order_id
        ORDER BY coi.crm_row_id
    """
    
    try:
        result = db.session.execute(text(query), {'crm_order_id': crm_order_id})
        rows = result.fetchall()
    except Exception as e:
        import traceback
        raise
    
    renglones = []
    for row in rows:
        # Obtener propuestas de pago para este renglón
        forma_pagos = obtener_forma_pagos_renglon(row.id)
        
        renglon = {
            'id': row.encabezado_detalle_recibir_id,
            'encabezado_detalle_recibir_id': row.encabezado_detalle_recibir_id,
            'item_id': row.item_id,
            'cantidad_recibida': row.cantidad_recibida,
            'precio': float(row.precio) if row.precio else 0.0,
            'precio_costo': float(row.precio_costo) if row.precio_costo else None,
            'comision': float(row.comision) if row.comision else None,
            'formaPagos': forma_pagos
        }
        renglones.append(renglon)
    
    return renglones


def obtener_forma_pagos_renglon(crm_order_item_id):
    """
    Obtiene las propuestas de forma de pago para un renglón.
    """
    from sqlalchemy import text
    
    query = """
        SELECT 
            coipp.payment_method_id as medio_pago_id,
            coipp.amount_without_formula as monto_sin_formula,
            coipp.amount_with_formula as monto_con_formula
        FROM crm_order_item_payment_proposals coipp
        WHERE coipp.crm_order_item_id = :crm_order_item_id
    """
    
    result = db.session.execute(text(query), {'crm_order_item_id': str(crm_order_item_id)})
    rows = result.fetchall()
    
    forma_pagos = []
    for row in rows:
        forma_pago = {
            'medio_pago_id': row.medio_pago_id,
            'monto_sin_formula': float(row.monto_sin_formula) if row.monto_sin_formula else 0.0,
            'monto_con_formula': float(row.monto_con_formula) if row.monto_con_formula else 0.0
        }
        forma_pagos.append(forma_pago)
    
    return forma_pagos


def obtener_pagos_procesados_venta(crm_order_id):
    """
    Obtiene los pagos procesados (acreditados) de una venta.
    """
    from sqlalchemy import text
    
    query = """
        SELECT 
            copp.crm_payment_id as id,
            copp.payment_method_id as forma_pago_id,
            copp.payment_method_description as forma_pago_descripcion,
            copp.coupon_value as valor_cupon,
            copp.credited_value as valor_acreditado,
            copp.difference as diferencia,
            copp.receipt_number as numero_comprobante,
            copp.collected_at as fecha_cobranza
        FROM crm_order_payments_processed copp
        WHERE copp.crm_order_id = :crm_order_id
        ORDER BY copp.crm_payment_id
    """
    
    try:
        result = db.session.execute(text(query), {'crm_order_id': crm_order_id})
        rows = result.fetchall()
    except Exception as e:
        import traceback
        raise
    
    pagos = []
    for row in rows:
        pago = {
            'id': row.id,
            'forma_pago_id': row.forma_pago_id,
            'forma_pago_descripcion': row.forma_pago_descripcion,
            'valor_cupon': float(row.valor_cupon) if row.valor_cupon else 0.0,
            'valor_acreditado': float(row.valor_acreditado) if row.valor_acreditado else 0.0,
            'diferencia': float(row.diferencia) if row.diferencia else 0.0,
            'numero_comprobante': row.numero_comprobante,
            'fecha_cobranza': row.fecha_cobranza.strftime('%Y-%m-%d %H:%M:%S') if row.fecha_cobranza else None
        }
        pagos.append(pago)
    
    return pagos


def obtener_vendedor_id_desde_api_secret(api_secret):
    """
    Obtiene el vendedor_id desde la variable de entorno VENDEDOR_ID.
    """
    return Config.VENDEDOR_ID


def calcular_numero_comprobante():
    """
    Calcula el siguiente numero_comprobante (receipt_number).
    Retorna: numero_comprobante
    Formato: numero_comprobante = "R-0001-000000001"
    """
    from sqlalchemy import text
    
    try:
        # Limpiar cualquier transacción abortada antes de la consulta
        try:
            db.session.rollback()
        except:
            pass
        
        # Obtener el último comprobante
        query = """
            SELECT receipt_number
            FROM crm_orders
            WHERE receipt_number LIKE 'R-%-%'
            ORDER BY crm_order_id DESC
            LIMIT 1
        """
        
        result = db.session.execute(text(query))
        row = result.fetchone()
        
        if row and row[0]:
            # Extraer el número del último comprobante (formato: R-0001-000000001)
            last_receipt = row[0]
            
            try:
                # Intentar extraer el número del formato R-XXXX-YYYYYYYYY
                parts = last_receipt.split('-')
                if len(parts) >= 3:
                    last_pto = parts[1]
                    last_num = parts[2]
                    
                    # Incrementar
                    next_pto = str(int(last_pto) + 1).zfill(4)
                    next_num = str(int(last_num) + 1).zfill(9)
                    
                    numero_comprobante = f"R-{next_pto}-{next_num}"
                    return numero_comprobante
            except (ValueError, IndexError):
                pass
        
        # Si no hay comprobantes anteriores, usar valores iniciales
        numero_comprobante = "R-0001-000000001"
        return numero_comprobante
    except Exception as e:
        # En caso de error, hacer rollback y usar valores por defecto
        try:
            db.session.rollback()
        except:
            pass
        return "R-0001-000000001"


def validar_cuit(cuit):
    """
    Valida solo el formato del CUIT.
    Formato esperado: XX-XXXXXXXX-X (13 caracteres)
    Retorna: (es_valido, mensaje_error)
    """
    if not cuit:
        return False, "El CUIT no puede estar vacío"
    
    # Validar formato básico
    if len(cuit) != 13:
        return False, "El formato del CUIT es inválido. Debe tener formato: XX-XXXXXXXX-X"
    
    if cuit[2] != '-' or cuit[11] != '-':
        return False, "El formato del CUIT es inválido. Debe tener formato: XX-XXXXXXXX-X"
    
    # Validar que las partes sean numéricas
    try:
        tipo = cuit[0:2]
        numero = cuit[3:11]
        verificador = cuit[12]
        
        # Verificar que todas las partes sean numéricas
        if not tipo.isdigit() or not numero.isdigit() or not verificador.isdigit():
            return False, "El CUIT contiene caracteres no numéricos"
        
        return True, None
    except (ValueError, IndexError):
        return False, "El formato del CUIT es inválido. Debe tener formato: XX-XXXXXXXX-X"


@public_api_bp.route('/api/ventas/crear', methods=['POST'])
@api_key_required
def crear_venta():
    """
    Endpoint para crear una nueva venta.
    
    Los campos vendedor_id y numero_comprobante se asignan automáticamente 
    y NO deben enviarse en el request.
    
    El vendedor_id se obtiene desde la variable de entorno VENDEDOR_ID.
    El numero_comprobante se calcula automáticamente basándose en el último comprobante.
    El crm_order_id se genera automáticamente como MAX(crm_order_id) + 1.
    
    Después de crear la venta exitosamente, se llama a sync_crm_ventas para sincronizar.
    """
    try:
        # Validar que se recibió un body
        if not request.is_json:
            return validation_error("El body debe ser JSON")
        
        data = request.get_json()
        if data is None:
            return validation_error("El body es requerido")
        
        # Guardar el payload original para enviarlo al endpoint externo
        payload_original = data.copy() if data else None
        
        # Obtener api_secret del token
        api_key = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                api_key = auth_header.split(' ')[1]
        
        # Obtener vendedor_id desde api_secret
        vendedor_id = obtener_vendedor_id_desde_api_secret(api_key)
        if not vendedor_id:
            return validation_error("No se pudo obtener el vendedor_id desde el api_secret")
        
        from sqlalchemy import text
        from datetime import datetime
        import re
        
        # ========================================================================
        # VALIDACIONES DE CAMPOS REQUERIDOS
        # ========================================================================
        campos_requeridos = {
            'fecha_detalle': 'La fecha de detalle es requerida',
            'tipo_venta': 'El tipo de venta es requerido',
            'cliente_nombre': 'El nombre del cliente es requerido',
            'cliente_direccion': 'La dirección del cliente es requerida',
            'tipo_documento_cliente': 'El tipo de documento del cliente es requerido',
            'cliente_telefono': 'El teléfono del cliente es requerido',
            'provincia_id': 'La provincia es requerida',
            'localidad': 'La localidad es requerida',
            'zona_id': 'La zona de entrega es requerida',
            'js': 'Los renglones (js) son requeridos'
        }
        
        for campo, mensaje in campos_requeridos.items():
            if campo not in data or data[campo] is None or (isinstance(data[campo], str) and not data[campo].strip()):
                return validation_error(mensaje)
        
        # Validar que js sea un array con al menos un elemento
        if not isinstance(data['js'], list) or len(data['js']) == 0:
            return validation_error("El campo js debe ser un array con al menos un renglón")
        
        # Validar que haya al menos un renglón con accion="N"
        renglones_nuevos = [r for r in data['js'] if r.get('accion') == 'N']
        if len(renglones_nuevos) == 0:
            return validation_error("Debe haber al menos un renglón con accion='N'")
        
        # ========================================================================
        # VALIDACIONES DE TIPO DE DOCUMENTO Y DOCUMENTO
        # ========================================================================
        tipo_documento = data['tipo_documento_cliente']
        documento_cliente = data.get('documento_cliente', '').strip()
        
        if tipo_documento == 1:  # DNI
            # Validar formato DNI (solo números)
            if documento_cliente:
                if not documento_cliente.isdigit():
                    return validation_error("El DNI debe contener solo números")
            
            # Validar compatibilidad con tipo_venta
            tipo_venta = data.get('tipo_venta')
            if tipo_venta and tipo_venta > 1:
                return jsonify({
                    "status": False,
                    "message": "Tipo de documento DNI no es compatible con tipo de venta mayor a 1"
                }), 422
            
            # Validar si algún medio de pago requiere DNI
            forma_pagos = data.get('formaPagos', [])
            requiere_dni = False
            for pago in forma_pagos:
                # Buscar si el medio de pago requiere DNI (pdf=0)
                query_medio = """
                    SELECT pdf
                    FROM crm_payment_methods
                    WHERE crm_payment_method_id = :medio_id
                """
                try:
                    result_medio = db.session.execute(
                        text(query_medio),
                        {'medio_id': pago.get('medios_pago_id')}
                    )
                    row_medio = result_medio.fetchone()
                    if row_medio and row_medio[0] == 0:
                        requiere_dni = True
                        break
                except:
                    db.session.rollback()
                    pass
            
            if requiere_dni and not documento_cliente:
                return validation_error("El documento del cliente es requerido porque algún medio de pago requiere DNI")
        
        elif tipo_documento == 2:  # CUIT
            # Validar que email_cliente esté presente
            email_cliente = data.get('email_cliente', '').strip()
            if not email_cliente:
                return jsonify({
                    "status": False,
                    "message": "El email del cliente es requerido para tipo de documento CUIT"
                }), 422
            
            # Validar formato y dígito verificador del CUIT
            if not documento_cliente:
                return validation_error("El documento del cliente es requerido para tipo CUIT")
            
            es_valido, mensaje_error = validar_cuit(documento_cliente)
            if not es_valido:
                return jsonify({
                    "status": False,
                    "message": mensaje_error
                }), 422
        
        # ========================================================================
        # VALIDACIONES DE PRODUCTOS (RENGLONES)
        # ========================================================================
        total_venta = 0.0
        productos_invalidos = []
        productos_sin_comision = []
        
        for idx, renglon in enumerate(data['js']):
            if renglon.get('accion') != 'N':
                continue
            
            # Validar campos requeridos del renglón
            if 'item_id' not in renglon:
                return validation_error(f"El campo item_id es requerido en el renglón {idx + 1}")
            
            item_id = renglon['item_id']
            cantidad = renglon.get('cantidad_recibida', 0)
            precio = renglon.get('precio', 0)
            unitario_sin_fpago = renglon.get('unitario_sin_fpago', 0)
            
            # Validar que cantidad y precio sean mayores a 0
            if cantidad <= 0:
                return validation_error(f"La cantidad debe ser mayor a 0 en el renglón {idx + 1}")
            if precio <= 0:
                return validation_error(f"El precio debe ser mayor a 0 en el renglón {idx + 1}")
            
            # Validar que el producto exista y esté activo en crm_products
            query_producto = """
                SELECT cp.crm_product_id, cp.is_active
                FROM crm_products cp
                WHERE cp.crm_product_id = :item_id
                LIMIT 1
            """
            
            try:
                result_producto = db.session.execute(
                    text(query_producto),
                    {'item_id': item_id}
                )
                row_producto = result_producto.fetchone()
                
                if not row_producto:
                    productos_invalidos.append(str(item_id))
                    continue
                
                if not row_producto[1]:  # is_active
                    productos_invalidos.append(str(item_id))
                    continue
                
                # Verificar comisión del vendedor
                # TODO: Implementar verificación de comisión según tipo de vendedor
                # Por ahora asumimos que existe comisión
                
            except Exception as e:
                db.session.rollback()
                productos_invalidos.append(str(item_id))
                continue
            
            total_venta += float(precio)
        
        if productos_invalidos:
            # Limpiar transacción antes de retornar error
            try:
                db.session.rollback()
            except:
                pass
            return jsonify({
                "status": False,
                "message": f"Uno o más productos no existen, están inactivos o fueron eliminados. IDs inválidos: {', '.join(productos_invalidos)}"
            }), 400
        
        if productos_sin_comision:
            productos_lista = '\n'.join([f" - {p}" for p in productos_sin_comision])
            return jsonify({
                "status": False,
                "message": f"Existe uno o más productos sin comisión asignada al tipo de vendedor. Lista de productos:\n{productos_lista}"
            }), 422
        
        # ========================================================================
        # VALIDACIONES DE ZONA
        # ========================================================================
        zona_id = data['zona_id']
        query_zona = """
            SELECT crm_zone_id
            FROM crm_delivery_zones
            WHERE crm_zone_id = :zona_id
        """
        
        try:
            result_zona = db.session.execute(text(query_zona), {'zona_id': zona_id})
            row_zona = result_zona.fetchone()
            
            if not row_zona:
                db.session.rollback()
                return jsonify({
                    "status": False,
                    "message": "La zona de entrega no existe o fue eliminada"
                }), 400
            
        except Exception:
            db.session.rollback()
            return jsonify({
                "status": False,
                "message": "La zona de entrega no existe o fue eliminada"
            }), 400
        
        # ========================================================================
        # VALIDACIONES DE PAGOS (FORMA PAGOS)
        # ========================================================================
        forma_pagos = data.get('formaPagos', [])
        if not isinstance(forma_pagos, list):
            return validation_error("El campo formaPagos debe ser un array")
        
        if len(forma_pagos) == 0:
            return validation_error("Debe haber al menos un medio de pago")
        
        total_pagos = 0.0
        
        for pago in forma_pagos:
            if 'medios_pago_id' not in pago:
                return validation_error("Cada pago debe tener medios_pago_id")
            
            if 'monto_total' not in pago:
                return validation_error("Cada pago debe tener monto_total")
            
            if 'procesado' not in pago:
                return validation_error("Cada pago debe tener procesado (true/false)")
            
            monto = float(pago['monto_total'])
            if monto <= 0:
                return validation_error("El monto_total de cada pago debe ser mayor a 0")
            
            total_pagos += monto
        
        # Validar que la suma de pagos coincida con el total de la venta
        diferencia = abs(total_pagos - total_venta)
        if diferencia > 0.01:  # Tolerancia de 1 centavo
            return jsonify({
                "status": False,
                "message": "La suma de los pagos no coincide con el total de la venta",
                "total_productos": total_venta,
                "total_pagos": total_pagos
            }), 422
        
        # ========================================================================
        # CALCULAR NUMERO COMPROBANTE
        # ========================================================================
        # Limpiar cualquier transacción abortada antes de calcular el comprobante
        try:
            db.session.rollback()
        except:
            pass
        
        numero_comprobante = calcular_numero_comprobante()
        
        # ========================================================================
        # CREAR VENTA (INSERT EN CRM_ORDERS)
        # ========================================================================
        # Limpiar cualquier transacción abortada antes del INSERT principal
        try:
            db.session.rollback()
        except:
            pass
        
        try:
            # Construir dirección completa
            cliente_direccion_completa = data['cliente_direccion']
            if data.get('cliente_direccion_barrio'):
                cliente_direccion_completa += f", {data['cliente_direccion_barrio']}"
            if data.get('cliente_direccion_mas_datos'):
                cliente_direccion_completa += f", {data['cliente_direccion_mas_datos']}"
            
            # Parsear fecha_detalle
            fecha_detalle = datetime.strptime(data['fecha_detalle'], '%Y-%m-%d').date()
            
            # Obtener el siguiente crm_order_id (usar secuencia o auto-incremental)
            # Por ahora, obtenemos el máximo y sumamos 1
            try:
                db.session.rollback()
            except:
                pass
            
            try:
                query_max_id = """
                    SELECT COALESCE(MAX(crm_order_id), 0) + 1
                    FROM crm_orders
                """
                result_max = db.session.execute(text(query_max_id))
                nuevo_crm_order_id = result_max.scalar()
            except Exception as e:
                # Si falla obtener el crm_order_id, hacer rollback y retornar error
                db.session.rollback()
                return jsonify({
                    "status": False,
                    "message": f"Error al obtener el siguiente ID de orden: {str(e)}"
                }), 400
            
            # Preparar datos para el campo raw (JSONB)
            raw_data = {
                'fecha_detalle': data['fecha_detalle'],
                'cliente_direccion_barrio': data.get('cliente_direccion_barrio'),
                'cliente_direccion_mas_datos': data.get('cliente_direccion_mas_datos'),
                'cel_alternativo': data.get('cel_alternativo'),
                'lat_long': data.get('lat_long'),
                'observaciones': data.get('observaciones'),
                'created_from': 'web_externa'
            }
            
            # Generar UUID para el campo id
            nuevo_uuid = uuid.uuid4()
            
            # Insertar en crm_orders
            insert_order = """
                INSERT INTO crm_orders (
                    id, crm_order_id, receipt_number, detail_date, crm_seller_id,
                    crm_sale_type_id, client_name, client_address,
                    client_phone, client_email, client_document,
                    crm_doc_type_id, crm_province_id, city,
                    crm_zone_id, status, total_sale, total_with_payment,
                    is_cancelled, delivery_date,
                    crm_created_at, crm_updated_at, raw
                ) VALUES (
                    :id, :crm_order_id, :receipt_number, :detail_date, :crm_seller_id,
                    :crm_sale_type_id, :client_name, :client_address,
                    :client_phone, :client_email, :client_document,
                    :crm_doc_type_id, :crm_province_id, :city,
                    :crm_zone_id, 'pendiente de entrega', :total_sale, :total_with_payment,
                    false, NULL,
                    NOW(), NOW(), CAST(:raw AS jsonb)
                ) RETURNING crm_order_id
            """
            
            try:
                result_order = db.session.execute(
                    text(insert_order),
                    {
                        'id': str(nuevo_uuid),
                        'crm_order_id': nuevo_crm_order_id,
                        'receipt_number': numero_comprobante,
                        'detail_date': fecha_detalle,
                        'crm_seller_id': vendedor_id,
                        'crm_sale_type_id': data['tipo_venta'],
                        'client_name': data['cliente_nombre'],
                        'client_address': cliente_direccion_completa,
                        'client_phone': data['cliente_telefono'],
                        'client_email': data.get('email_cliente'),
                        'client_document': documento_cliente if documento_cliente else None,
                        'crm_doc_type_id': tipo_documento,
                        'crm_province_id': data['provincia_id'],
                        'city': data['localidad'],
                        'crm_zone_id': zona_id,
                        'total_sale': total_venta,
                        'total_with_payment': total_pagos,
                        'raw': json.dumps(raw_data)
                    }
                )
                
                crm_order_id = result_order.fetchone()[0]
            except Exception as e:
                # Si falla el INSERT de crm_orders, hacer rollback y retornar error
                db.session.rollback()
                error_msg = str(e)
                # Verificar si es un error de foreign key para dar mensaje más específico
                if 'ForeignKeyViolation' in error_msg or 'foreign key' in error_msg.lower():
                    if 'crm_province' in error_msg:
                        return jsonify({
                            "status": False,
                            "message": f"La provincia con ID {data['provincia_id']} no existe en el CRM"
                        }), 400
                    elif 'crm_doc_type' in error_msg:
                        return jsonify({
                            "status": False,
                            "message": f"El tipo de documento con ID {tipo_documento} no existe en el CRM"
                        }), 400
                    elif 'crm_sale_type' in error_msg:
                        return jsonify({
                            "status": False,
                            "message": f"El tipo de venta con ID {data['tipo_venta']} no existe en el CRM"
                        }), 400
                    elif 'crm_zone' in error_msg:
                        return jsonify({
                            "status": False,
                            "message": f"La zona con ID {zona_id} no existe en el CRM"
                        }), 400
                
                # Error genérico
                raise
            
            # ====================================================================
            # CREAR RENGLONES (CRM_ORDER_ITEMS)
            # ====================================================================
            order_items_ids = []
            crm_row_id_counter = 1  # Contador para crm_row_id si no viene en el renglón
            
            for renglon in data['js']:
                if renglon.get('accion') != 'N':
                    continue
                
                item_id = renglon['item_id']
                cantidad = renglon['cantidad_recibida']
                precio = renglon['precio']
                unitario_sin_fpago = renglon.get('unitario_sin_fpago', precio / cantidad if cantidad > 0 else 0)
                descripcion = renglon.get('descripcion', '')
                
                # crm_row_id viene del js[].id si existe, sino usar contador incremental
                crm_row_id = renglon.get('id') if renglon.get('id') is not None else crm_row_id_counter
                if renglon.get('id') is None:
                    crm_row_id_counter += 1
                
                # crm_product_id: usar item_id si corresponde a un producto CRM
                crm_product_id = item_id if isinstance(item_id, int) else None
                
                # Precio de costo (por ahora None, se puede obtener desde crm_products si existe ese campo)
                precio_costo = None
                
                # Calcular comisión (TODO: Implementar cálculo real según tipo de vendedor)
                comision = None
                
                # Preparar datos para el campo raw (JSONB)
                raw_item_data = {
                    'descripcion': descripcion,
                    'unitario_sin_fpago': unitario_sin_fpago,
                    'accion': renglon.get('accion', 'N')
                }
                
                # Generar UUID para el campo id de crm_order_items
                nuevo_item_uuid = uuid.uuid4()
                
                insert_item = """
                    INSERT INTO crm_order_items (
                        id, crm_order_id, crm_row_id, 
                        crm_product_id, item_id,
                        quantity, price, cost_price, commission,
                        raw, created_at, updated_at
                    ) VALUES (
                        :id, :crm_order_id, :crm_row_id,
                        :crm_product_id, :item_id,
                        :quantity, :price, :cost_price, :commission,
                        CAST(:raw AS jsonb), NOW(), NOW()
                    ) RETURNING id
                """
                
                try:
                    result_item = db.session.execute(
                        text(insert_item),
                        {
                            'id': str(nuevo_item_uuid),
                            'crm_order_id': crm_order_id,
                            'crm_row_id': crm_row_id,
                            'crm_product_id': crm_product_id,
                            'item_id': item_id,
                            'quantity': cantidad,
                            'price': precio,
                            'cost_price': precio_costo,
                            'commission': comision,
                            'raw': json.dumps(raw_item_data)
                        }
                    )
                    
                    order_item_id = result_item.fetchone()[0]
                    order_items_ids.append({
                        'id': order_item_id,
                        'crm_row_id': crm_row_id,
                        'precio': precio,
                        'item_id': item_id
                    })
                except Exception as e:
                    # Si falla el INSERT de un item, hacer rollback y retornar error
                    db.session.rollback()
                    error_msg = str(e)
                    return jsonify({
                        "status": False,
                        "message": f"Error al crear el renglón del producto {item_id}: {error_msg}"
                    }), 400
            
            # ====================================================================
            # PROCESAR PAGOS (FORMA PAGOS A NIVEL DE ENCABEZADO)
            # ====================================================================
            try:
                # Verificar que la transacción esté activa antes de procesar pagos
                db.session.execute(text("SELECT 1"))
            except Exception as e:
                # Si la transacción está abortada, hacer rollback y retornar error
                db.session.rollback()
                return jsonify({
                    "status": False,
                    "message": f"Error: La transacción está abortada antes de procesar pagos. Error: {str(e)}"
                }), 400
            
            # Los pagos se distribuyen proporcionalmente por producto
            # Calcular proporción de cada renglón
            proporciones = []
            for item in order_items_ids:
                proporcion = item['precio'] / total_venta if total_venta > 0 else 0
                proporciones.append({
                    'order_item_id': item['id'],
                    'proporcion': proporcion
                })
            
            # Procesar cada forma de pago
            for pago in forma_pagos:
                medio_pago_id = pago['medios_pago_id']
                monto_total = float(pago['monto_total'])
                procesado = pago.get('procesado', False)
                
                # Distribuir el pago proporcionalmente entre los renglones
                for idx, prop in enumerate(proporciones):
                    monto_renglon = monto_total * prop['proporcion']
                    
                    # Preparar datos para el campo raw (JSONB)
                    raw_propuesta_data = {
                        'monto_total': monto_total,
                        'procesado': procesado
                    }
                    
                    # Generar UUID para el campo id de crm_order_item_payment_proposals
                    nuevo_propuesta_uuid = uuid.uuid4()
                    
                    # Insertar en crm_order_item_payment_proposals
                    insert_propuesta = """
                        INSERT INTO crm_order_item_payment_proposals (
                            id, crm_order_item_id, payment_method_id,
                            amount_without_formula, amount_with_formula,
                            raw, created_at, updated_at
                        ) VALUES (
                            :id, :crm_order_item_id, :payment_method_id,
                            :amount_without, :amount_with,
                            CAST(:raw AS jsonb), NOW(), NOW()
                        )
                    """
                    
                    try:
                        result_propuesta = db.session.execute(
                            text(insert_propuesta),
                            {
                                'id': str(nuevo_propuesta_uuid),
                                'crm_order_item_id': prop['order_item_id'],
                                'payment_method_id': medio_pago_id,
                                'amount_without': monto_renglon,
                                'amount_with': monto_renglon,
                                'raw': json.dumps(raw_propuesta_data)
                            }
                        )
                        # Verificar que la ejecución fue exitosa
                        if hasattr(result_propuesta, 'rowcount') and result_propuesta.rowcount == 0:
                            raise Exception("No se insertó ninguna fila en crm_order_item_payment_proposals")
                    except Exception as e:
                        # Si falla el INSERT de propuesta de pago, hacer rollback y retornar error
                        db.session.rollback()
                        error_msg = str(e)
                        # Verificar si es un error de foreign key para dar mensaje más específico
                        if 'ForeignKeyViolation' in error_msg or 'foreign key' in error_msg.lower():
                            if 'crm_order_item' in error_msg:
                                return jsonify({
                                    "status": False,
                                    "message": f"Error: El item de orden con ID {prop['order_item_id']} no existe. Esto no debería ocurrir."
                                }), 400
                        return jsonify({
                            "status": False,
                            "message": f"Error al crear la propuesta de pago para item {prop['order_item_id']}: {error_msg}"
                        }), 400
                
                # Si el pago está procesado, insertar en crm_order_payments_processed
                if procesado:
                    numero_comprobante_pago = pago.get('numero_comprobante')
                    fecha_cobranza = pago.get('fecha_cobranza')
                    
                    # Descripción del medio de pago (no validamos medios de pago, usar valor por defecto)
                    medio_desc = f"Medio {medio_pago_id}"
                    
                    # Obtener el siguiente crm_payment_id (usar secuencia o auto-incremental)
                    # Verificar que la transacción esté activa antes de continuar
                    try:
                        # Intentar ejecutar una query simple para verificar el estado de la transacción
                        db.session.execute(text("SELECT 1"))
                    except Exception as e:
                        # Si la transacción está abortada, hacer rollback y retornar error
                        db.session.rollback()
                        return jsonify({
                            "status": False,
                            "message": f"Error: La transacción está abortada. Error previo: {str(e)}"
                        }), 400
                    
                    try:
                        query_max_payment_id = """
                            SELECT COALESCE(MAX(crm_payment_id), 0) + 1
                            FROM crm_order_payments_processed
                        """
                        result_max_payment = db.session.execute(text(query_max_payment_id))
                        nuevo_crm_payment_id = result_max_payment.scalar()
                    except Exception as e:
                        # Si la transacción está abortada, hacer rollback y retornar error
                        db.session.rollback()
                        return jsonify({
                            "status": False,
                            "message": f"Error al obtener el siguiente ID de pago: {str(e)}"
                        }), 400
                    
                    # Calcular costos (TODO: Implementar cálculo real de cupones y costos)
                    valor_cupon = 0.0
                    valor_acreditado = monto_total
                    diferencia = 0.0
                    
                    # Preparar datos para el campo raw (JSONB)
                    raw_pago_data = {
                        'numero_comprobante': numero_comprobante_pago,
                        'fecha_cobranza': fecha_cobranza,
                        'procesado': procesado
                    }
                    
                    # Generar UUID para el campo id de crm_order_payments_processed
                    nuevo_pago_uuid = uuid.uuid4()
                    
                    insert_procesado = """
                        INSERT INTO crm_order_payments_processed (
                            id, crm_payment_id, crm_order_id, payment_method_id, payment_method_description,
                            coupon_value, credited_value, difference,
                            receipt_number, collected_at, raw, created_at, updated_at
                        ) VALUES (
                            :id, :crm_payment_id, :crm_order_id, :payment_method_id, :payment_method_description,
                            :coupon_value, :credited_value, :difference,
                            :receipt_number, :collected_at, CAST(:raw AS jsonb), NOW(), NOW()
                        )
                    """
                    
                    fecha_cobranza_parsed = None
                    if fecha_cobranza:
                        try:
                            fecha_cobranza_parsed = datetime.strptime(fecha_cobranza, '%Y-%m-%d').date()
                        except:
                            pass
                    
                    try:
                        db.session.execute(
                            text(insert_procesado),
                            {
                                'id': str(nuevo_pago_uuid),
                                'crm_payment_id': nuevo_crm_payment_id,
                                'crm_order_id': crm_order_id,
                                'payment_method_id': medio_pago_id,
                                'payment_method_description': medio_desc,
                                'coupon_value': valor_cupon,
                                'credited_value': valor_acreditado,
                                'difference': diferencia,
                                'receipt_number': numero_comprobante_pago,
                                'collected_at': fecha_cobranza_parsed,
                                'raw': json.dumps(raw_pago_data)
                            }
                        )
                    except Exception as e:
                        # Si falla el INSERT de pago procesado, hacer rollback y retornar error
                        db.session.rollback()
                        error_msg = str(e)
                        # Verificar si es un error de foreign key
                        if 'ForeignKeyViolation' in error_msg or 'foreign key' in error_msg.lower():
                            if 'crm_order' in error_msg:
                                return jsonify({
                                    "status": False,
                                    "message": f"Error: La venta con ID {crm_order_id} no existe. Esto no debería ocurrir."
                                }), 400
                        return jsonify({
                            "status": False,
                            "message": f"Error al crear el pago procesado: {error_msg}"
                        }), 400
            
            # Commit de la transacción
            db.session.commit()
            
            # ====================================================================
            # LLAMAR A SYNC_CRM_VENTAS
            # ====================================================================
            try:
                # Construir el JSON para sync_crm_ventas
                # La función espera el formato estándar de sincronización
                sync_data = {
                    "tipo": "ventas",
                    "datos": [{
                        "id": crm_order_id,
                        "estado": "pendiente de entrega",
                        # Agregar otros campos necesarios si la función los requiere
                    }],
                    "status": True,
                    "filtros": {},
                    "sincronizar": {
                        "accion": "create",
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                }
                
                from sqlalchemy.dialects.postgresql import JSONB
                from sqlalchemy import bindparam
                
                # Llamar a sync_crm_ventas
                result_sync = db.session.execute(
                    text("SELECT * FROM sync_crm_ventas(:json_data)").bindparams(
                        bindparam('json_data', type_=JSONB)
                    ),
                    {"json_data": sync_data}
                )
                
                # Procesar resultados si es necesario
                rows_sync = result_sync.fetchall()
                
                # Commit de la sincronización
                db.session.commit()
                
            except Exception as sync_error:
                # Si falla la sincronización, hacer rollback y continuar
                # La venta ya está creada, así que hacemos rollback del sync y continuamos
                db.session.rollback()
                # Re-hacer commit de la venta si es necesario
                # Por ahora solo registramos el error pero no fallamos la creación
                import traceback
                print(f"Advertencia: Error al sincronizar venta después de crear: {str(sync_error)}")
                print(traceback.format_exc())
            
            # ====================================================================
            # LLAMAR AL ENDPOINT EXTERNO PARA CREAR LA VENTA
            # ====================================================================
            external_response_info = None
            external_venta_id = None  # ID que retorna el endpoint externo
            
            try:
                # Enviar el payload original (misma estructura que recibimos) al endpoint externo
                if not payload_original:
                    print(f"Advertencia: No hay payload original para enviar al endpoint externo")
                    external_response_info = {
                        "success": False,
                        "error": "No hay payload original para enviar",
                        "status_code": None,
                        "response": None
                    }
                else:
                    # Construir payload para enviar al endpoint externo con solo los campos requeridos
                    payload_externo = {
                        "fecha_detalle": data.get('fecha_detalle'),
                        "tipo_venta": data.get('tipo_venta'),
                        "cliente_nombre": data.get('cliente_nombre'),
                        "cliente_direccion": data.get('cliente_direccion'),
                        "tipo_documento_cliente": data.get('tipo_documento_cliente'),
                        "documento_cliente": data.get('documento_cliente', ''),
                        "cliente_telefono": data.get('cliente_telefono'),
                        "email_cliente": data.get('email_cliente'),
                        "provincia_id": data.get('provincia_id'),
                        "localidad": data.get('localidad'),
                        "zona_id": data.get('zona_id')
                    }
                    
                    # Normalizar el formato del CUIT si existe
                    if payload_externo.get('tipo_documento_cliente') == 2 and payload_externo.get('documento_cliente'):
                        documento = payload_externo.get('documento_cliente', '').strip()
                        # Si el CUIT no tiene el formato correcto, intentar normalizarlo
                        if documento and len(documento.replace('-', '').replace('.', '')) == 11:
                            # Remover guiones y puntos existentes
                            doc_limpio = documento.replace('-', '').replace('.', '')
                            if doc_limpio.isdigit():
                                # Formatear como XX-XXXXXXXX-X
                                documento_formateado = f"{doc_limpio[:2]}-{doc_limpio[2:10]}-{doc_limpio[10:]}"
                                payload_externo['documento_cliente'] = documento_formateado
                                print(f"DEBUG: CUIT normalizado de '{documento}' a '{documento_formateado}'")
                        
                        # Validar el formato después de normalizar
                        es_valido, mensaje_error = validar_cuit(payload_externo['documento_cliente'])
                        if not es_valido:
                            print(f"ADVERTENCIA: CUIT aún inválido después de normalizar: {payload_externo['documento_cliente']}")
                            print(f"Error: {mensaje_error}")
                    
                    # Construir el array js con la estructura exacta esperada
                    js_array = []
                    for renglon in data.get('js', []):
                        if renglon.get('accion') == 'N':
                            js_item = {
                                "id": None,
                                "accion": "N",
                                "item_id": renglon.get('item_id'),
                                "cantidad_recibida": renglon.get('cantidad_recibida'),
                                "precio": float(renglon.get('precio', 0)),
                                "unitario_sin_fpago": float(renglon.get('unitario_sin_fpago', 0)),
                                "descripcion": renglon.get('descripcion', '')
                            }
                            js_array.append(js_item)
                    payload_externo["js"] = js_array
                    
                    # Construir el array formaPagos con la estructura exacta esperada
                    forma_pagos_array = []
                    for pago in data.get('formaPagos', []):
                        forma_pago_item = {
                            "medios_pago_id": pago.get('medios_pago_id'),
                            "monto_total": float(pago.get('monto_total', 0)),
                            "procesado": bool(pago.get('procesado', False))
                        }
                        forma_pagos_array.append(forma_pago_item)
                    payload_externo["formaPagos"] = forma_pagos_array
                    
                    # Token de autorización
                    external_token = "e38f6bce99529961a5cffd3521c5abfea47b4ca3a1e2ff9d7f837a3155d4fa60"
                    
                    # URL del endpoint externo
                    external_url = "https://pruebas.bausing.com.ar/api/ventas/crear"
                    
                    # Headers
                    headers = {
                        "Authorization": f"Bearer {external_token}",
                        "Content-Type": "application/json"
                    }
                    
                    print(f"DEBUG: Enviando venta al endpoint externo...")
                    print(f"DEBUG: URL: {external_url}")
                    print(f"DEBUG: Payload keys: {list(payload_externo.keys())}")
                    if payload_externo.get('documento_cliente'):
                        print(f"DEBUG: documento_cliente: {payload_externo.get('documento_cliente')}")
                    
                    # Hacer la llamada POST con el payload preparado
                    response = requests.post(
                        external_url,
                        json=payload_externo,
                        headers=headers,
                        timeout=30  # Timeout de 30 segundos
                    )
                    
                    # Capturar información de la respuesta
                    response_text = None
                    response_json = None
                    try:
                        response_text = response.text
                        try:
                            response_json = response.json()
                        except:
                            pass
                    except:
                        pass
                    
                    external_response_info = {
                        "success": response.status_code in [200, 201],
                        "status_code": response.status_code,
                        "response_text": response_text,
                        "response_json": response_json,
                        "headers": dict(response.headers) if hasattr(response, 'headers') else None
                    }
                    
                    # Verificar el código de respuesta
                    if response.status_code not in [200, 201]:
                        print(f"Advertencia: El endpoint externo retornó código {response.status_code}")
                        print(f"Respuesta completa: {response_text}")
                    else:
                        print(f"Éxito: Venta enviada al endpoint externo correctamente")
                        print(f"Respuesta completa: {response_text}")
                        
                        # Extraer el venta_id de la respuesta del endpoint externo
                        # Según la documentación, la respuesta tiene esta estructura:
                        # {
                        #   "status": true,
                        #   "message": "Venta creada exitosamente",
                        #   "venta_id": 12345,
                        #   "numero_comprobante": "R-0001-000000123",
                        #   "timestamp": "2024-01-15 10:30:00"
                        # }
                        if response_json:
                            # Intentar obtener venta_id desde el root del JSON
                            external_venta_id = response_json.get('venta_id')
                            
                            # Si no está en el root, intentar desde data
                            if not external_venta_id and 'data' in response_json:
                                external_venta_id = response_json.get('data', {}).get('venta_id') or response_json.get('data', {}).get('crm_order_id')
                            
                            if external_venta_id:
                                print(f"INFO: El endpoint externo retornó venta_id: {external_venta_id}")
                            else:
                                print(f"ADVERTENCIA: No se pudo extraer venta_id de la respuesta del endpoint externo")
                                print(f"Respuesta JSON completa: {response_json}")
                        
            except requests.exceptions.RequestException as req_error:
                # Error de conexión o timeout
                import traceback
                error_traceback = traceback.format_exc()
                print(f"Advertencia: Error al llamar al endpoint externo: {str(req_error)}")
                print(error_traceback)
                external_response_info = {
                    "success": False,
                    "error": str(req_error),
                    "error_type": type(req_error).__name__,
                    "status_code": None,
                    "response": None,
                    "traceback": error_traceback
                }
            except Exception as ext_error:
                # Cualquier otro error
                import traceback
                error_traceback = traceback.format_exc()
                print(f"Advertencia: Error inesperado al llamar al endpoint externo: {str(ext_error)}")
                print(error_traceback)
                external_response_info = {
                    "success": False,
                    "error": str(ext_error),
                    "error_type": type(ext_error).__name__,
                    "status_code": None,
                    "response": None,
                    "traceback": error_traceback
                }
            
            # Retornar respuesta exitosa incluyendo información del endpoint externo
            # Usar el venta_id del endpoint externo si está disponible, sino el crm_order_id local
            venta_id_final = external_venta_id if external_venta_id else crm_order_id
            
            # Si el endpoint externo falló, incluir mensaje de advertencia
            mensaje_respuesta = "Venta creada exitosamente"
            if external_response_info and not external_response_info.get('success'):
                response_json = external_response_info.get('response_json')
                if isinstance(response_json, dict):
                    mensaje_error_externo = response_json.get('message') or external_response_info.get('error')
                else:
                    mensaje_error_externo = external_response_info.get('error')
                if mensaje_error_externo:
                    mensaje_respuesta = f"Venta creada localmente, pero falló en endpoint externo: {mensaje_error_externo}"
            
            response_data = {
                "crm_order_id": venta_id_final,
                "numero_comprobante": numero_comprobante
            }
            
            # Agregar información del endpoint externo a la respuesta
            if external_response_info:
                response_data["external_api"] = external_response_info
            
            # Si el endpoint externo falló con un error de validación, retornar código de error apropiado
            if external_response_info and not external_response_info.get('success'):
                status_code_externo = external_response_info.get('status_code')
                if status_code_externo in [400, 422]:
                    # Error de validación del endpoint externo
                    return jsonify({
                        "status": False,
                        "message": mensaje_error_externo or "Error al crear venta en endpoint externo",
                        "data": response_data
                    }), status_code_externo
            
            return success_response(
                data=response_data,
                message=mensaje_respuesta
            )
            
        except Exception as e:
            db.session.rollback()
            import traceback
            error_traceback = traceback.format_exc()
            print(f"ERROR al crear la venta: {str(e)}")
            print(f"Traceback completo:\n{error_traceback}")
            return processing_error(f"Error al crear la venta: {str(e)}")
            
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"ERROR del servidor: {str(e)}")
        print(f"Traceback completo:\n{error_traceback}")
        return server_error(f"Error del servidor: {str(e)}")
