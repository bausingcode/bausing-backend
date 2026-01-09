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
    - Si tipo es "ventas": usa la función sync_crm_ventas (detecta cambios de estado)
    - Si tipo es "medios_pago": omite la sincronización (simulado)
    
    Request Body:
    {
        "tipo": "productos" | "zonas" | "provincias" | "tipos_documento" | "ventas" | "medios_pago",
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
        elif tipo == 'ventas':
            function_name = 'sync_crm_ventas'
        else:
            return validation_error(f"Tipo '{tipo}' no soportado. Tipos válidos: productos, zonas, provincias, tipos_documento, ventas, medios_pago")
        
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
