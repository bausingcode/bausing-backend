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
from datetime import datetime, timedelta
from decimal import Decimal
from models.user import User
from models.wallet import Wallet, WalletMovement
from utils.email_service import email_service

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
    - Si tipo es "stock": acepta notificaciones de cambios de stock (solo update)
    
    Request Body:
    {
        "tipo": "productos" | "zonas" | "provincias" | "tipos_documento" | "tipos_venta" | "ventas" | "medios_pago" | "stock",
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
    print("=" * 80)
    print("[DEBUG] /public/sincronizar - Llamada recibida")
    print(f"[DEBUG] Método: {request.method}")
    print(f"[DEBUG] Headers: {dict(request.headers)}")
    print(f"[DEBUG] Remote Address: {request.remote_addr}")
    print(f"[DEBUG] Timestamp: {datetime.now().isoformat()}")
    print("=" * 80)
    
    try:
        # Validar que se recibió un body
        if not request.is_json:
            print("[DEBUG] Error: El body debe ser JSON")
            return validation_error("El body debe ser JSON")
        
        body_data = request.get_json()
        
        if body_data is None:
            print("[DEBUG] Error: El body es requerido")
            return validation_error("El body es requerido")
        
        # Debug completo: ayuda a detectar mismatches de shape/keys en payload
        try:
            import json
            print("[DEBUG] Body completo recibido (JSON):")
            print(json.dumps(body_data, ensure_ascii=True, default=str))
        except Exception as debug_json_error:
            print(f"[DEBUG] No se pudo imprimir JSON completo: {str(debug_json_error)}")
            print(f"[DEBUG] Body (repr): {repr(body_data)}")
        
        print(f"[DEBUG] Body recibido - Tipo: {body_data.get('tipo', 'N/A')}")
        print(f"[DEBUG] Body recibido - Cantidad de datos: {len(body_data.get('datos', [])) if isinstance(body_data.get('datos'), list) else 'N/A'}")
        print(f"[DEBUG] Body recibido - Sincronizar: {body_data.get('sincronizar', {})}")
        
        # Validar estructura básica
        if 'tipo' not in body_data:
            print("[DEBUG] Error: El campo 'tipo' es requerido")
            return validation_error("El campo 'tipo' es requerido")
        
        if 'datos' not in body_data:
            print("[DEBUG] Error: El campo 'datos' es requerido")
            return validation_error("El campo 'datos' es requerido")
        
        if 'sincronizar' not in body_data:
            print("[DEBUG] Error: El campo 'sincronizar' es requerido")
            return validation_error("El campo 'sincronizar' es requerido")
        
        tipo = body_data.get('tipo')
        print(f"[DEBUG] Procesando sincronización de tipo: {tipo}")
        
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
        elif tipo == 'stock':
            # Stock se procesa directamente sin función SQL
            # Procesar los datos de stock recibidos
            try:
                from sqlalchemy import text
                datos_stock = body_data.get('datos', [])
                
                if not datos_stock:
                    return success_response(
                        data={},
                        message="Sincronización de stock recibida correctamente (sin datos para actualizar)"
                    )
                
                # Actualizar el estado de stock de cada producto
                # IMPORTANTE: Solo se actualiza el campo 'stock' (boolean), NO se actualiza descripción ni otros campos
                productos_actualizados = 0
                for producto_stock in datos_stock:
                    producto_id = producto_stock.get('id')
                    estado = producto_stock.get('estado')  # "habilitado" o "inhabilitado"
                    
                    if not producto_id or not estado:
                        continue
                    
                    # Verificar si el producto existe y obtener solo el stock actual
                    # No necesitamos otros campos como descripción o min_limit
                    check_query = text("""
                        SELECT crm_product_id, stock
                        FROM crm_products
                        WHERE crm_product_id = :producto_id
                    """)
                    check_result = db.session.execute(check_query, {'producto_id': producto_id})
                    producto_existente = check_result.fetchone()
                    
                    if producto_existente:
                        # El campo stock es boolean, no integer
                        stock_actual_boolean = bool(producto_existente.stock) if producto_existente.stock is not None else False
                        
                        # Convertir el estado recibido a booleano
                        # "habilitado" = true, "inhabilitado" = false
                        nuevo_stock_boolean = (estado == "habilitado")
                        
                        # Si el estado recibido es diferente al estado actual, actualizar SOLO el stock
                        if nuevo_stock_boolean != stock_actual_boolean:
                            # Actualizar SOLO el campo stock (booleano) en crm_products
                            # NO se actualiza descripción ni ningún otro campo
                            update_query = text("""
                                UPDATE crm_products
                                SET stock = :nuevo_stock,
                                    crm_updated_at = NOW()
                                WHERE crm_product_id = :producto_id
                            """)
                            db.session.execute(update_query, {
                                'nuevo_stock': nuevo_stock_boolean,
                                'producto_id': producto_id
                            })
                            print(f"📦 Stock actualizado - Producto ID: {producto_id}, Estado: {estado}, Stock: {stock_actual_boolean} -> {nuevo_stock_boolean}")
                        else:
                            # El estado ya coincide, solo actualizamos la fecha de actualización
                            update_query = text("""
                                UPDATE crm_products
                                SET crm_updated_at = NOW()
                                WHERE crm_product_id = :producto_id
                            """)
                            db.session.execute(update_query, {'producto_id': producto_id})
                            print(f"📦 Notificación de stock - Producto ID: {producto_id}, Estado: {estado} (ya estaba actualizado)")
                        
                        productos_actualizados += 1
                    else:
                        print(f"⚠️ Producto ID {producto_id} no encontrado en crm_products")
                
                db.session.commit()
                
                return success_response(
                    data={'productos_actualizados': productos_actualizados},
                    message=f"Sincronización de stock recibida correctamente ({productos_actualizados} productos procesados)"
                )
                
            except Exception as e:
                db.session.rollback()
                return processing_error(f"Error al procesar sincronización de stock: {str(e)}")
        else:
            return validation_error(f"Tipo '{tipo}' no soportado. Tipos válidos: productos, zonas, provincias, tipos_documento, tipos_venta, ventas, medios_pago, stock")
        
        print(f"[DEBUG] SQL function a ejecutar: {function_name}")
        
        # Llamar a la función correspondiente
        try:
            from sqlalchemy import text, bindparam
            from sqlalchemy.dialects.postgresql import JSONB
            import time
            
            # Para ventas, necesitamos obtener estados anteriores ANTES de sincronizar
            # Hacerlo en una transacción separada para evitar conflictos
            estados_anteriores = {}
            # En otros tipos (ej: productos/zonas) no existe orders_to_update,
            # pero más abajo se chequea igualmente. Evitamos NameError.
            orders_to_update = []
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
                sql_start = time.time()
                result = db.session.execute(
                    text(f"SELECT * FROM {function_name}(:json_data)").bindparams(
                        bindparam('json_data', type_=JSONB)
                    ),
                    {"json_data": body_data}
                )
                print(f"[DEBUG] SQL ejecutado (ventas) - elapsed={time.time() - sql_start:.3f}s")
                
                # Procesar resultados y detectar cambios de estado
                rows = result.fetchall()
                orders_to_update = []  # Lista para guardar las órdenes que necesitan actualización
                
                for row in rows:
                    crm_order_id = row[0]  # p_crm_order_id
                    nuevo_estado = row[1]   # delivery_status
                    accion = row[2]         # affected
                    
                    print(f"[DEBUG sync] Procesando venta: crm_order_id={crm_order_id}, nuevo_estado='{nuevo_estado}'")
                    
                    # Si el estado es "finalizado", marcar payment_processed como true en la tabla orders
                    # Normalizar el estado para comparación (lowercase y sin espacios)
                    estado_normalizado = nuevo_estado.lower().strip() if nuevo_estado else ""
                    if estado_normalizado == "finalizado":
                        try:
                            from models.order import Order
                            order = Order.query.filter_by(crm_order_id=crm_order_id).first()
                            if order:
                                if not order.payment_processed:
                                    order.payment_processed = True
                                    orders_to_update.append(order)
                                    print(f"✅ Marcado payment_processed=True para orden con crm_order_id={crm_order_id} (estado: {nuevo_estado})")
                                    
                                    # Procesar crédito de referido si la orden tiene código de referido
                                    if order.referral_code_used:
                                        try:
                                            from routes.referrals import process_referral_credit
                                            process_referral_credit(order)
                                            print(f"✅ Procesado crédito de referido para orden {order.id} desde sincronización CRM")
                                        except Exception as referral_error:
                                            import traceback
                                            print(f"⚠️ Error al procesar crédito de referido desde sincronización: {str(referral_error)}")
                                            print(traceback.format_exc())
                                else:
                                    print(f"ℹ️  Orden con crm_order_id={crm_order_id} ya tenía payment_processed=True")
                            else:
                                print(f"⚠️  No se encontró orden con crm_order_id={crm_order_id} para marcar como pagado")
                        except Exception as payment_error:
                            # No fallar la sincronización si falla la actualización de payment_processed
                            import traceback
                            print(f"❌ Error al actualizar payment_processed: {str(payment_error)}")
                            print(traceback.format_exc())
                    
                    # Obtener estado anterior
                    estado_anterior = estados_anteriores.get(crm_order_id)
                    
                    # Si el estado cambió, hacer print y enviar email
                    if estado_anterior and estado_anterior != nuevo_estado:
                        print(f"⚠️ CAMBIO DE ESTADO - Venta ID: {crm_order_id}")
                        print(f"   Estado anterior: {estado_anterior}")
                        print(f"   Estado nuevo: {nuevo_estado}")
                        print(f"   Acción: {accion}")
                        
                        # Obtener información del cliente para enviar email
                        try:
                            cliente_query = text("""
                                SELECT client_email, client_name, receipt_number
                                FROM crm_orders
                                WHERE crm_order_id = :order_id
                            """)
                            cliente_result = db.session.execute(
                                cliente_query,
                                {"order_id": crm_order_id}
                            )
                            cliente_row = cliente_result.fetchone()
                            
                            if cliente_row and cliente_row[0]:  # Si existe client_email
                                client_email = cliente_row[0]
                                client_name = cliente_row[1] or "Cliente"
                                receipt_number = cliente_row[2]
                                
                                # Enviar email de notificación de estado
                                from utils.email_service import email_service
                                email_service.send_delivery_status_email(
                                    client_email=client_email,
                                    client_name=client_name,
                                    estado=nuevo_estado,
                                    order_number=receipt_number
                                )
                                print(f"✅ Email de notificación enviado a {client_email}")
                            else:
                                print(f"⚠️ No se encontró client_email para la venta {crm_order_id}")
                        except Exception as email_error:
                            # No fallar la sincronización si falla el envío de email
                            print(f"❌ Error al enviar email de notificación: {str(email_error)}")
            else:
                # Otras funciones retornan void o un valor simple
                sql_start = time.time()
                result = db.session.execute(
                    text(f"SELECT {function_name}(:json_data)").bindparams(
                        bindparam('json_data', type_=JSONB)
                    ),
                    {"json_data": body_data}
                )
                print(f"[DEBUG] SQL ejecutado ({tipo}) - elapsed={time.time() - sql_start:.3f}s")
            
            # Hacer flush antes del commit para asegurar que los cambios de payment_processed se persistan
            if orders_to_update:
                try:
                    db.session.flush()
                    print(f"[DEBUG sync] Haciendo flush de {len(orders_to_update)} órdenes actualizadas")
                except Exception as flush_error:
                    print(f"⚠️  Error en flush: {str(flush_error)}")
            
            db.session.commit()
            
            # Verificar que los cambios se persistieron correctamente
            if orders_to_update:
                try:
                    from models.order import Order
                    for order in orders_to_update:
                        # Refrescar la orden desde la base de datos
                        db.session.refresh(order)
                        if order.payment_processed:
                            print(f"✅ Verificado: payment_processed=True para orden crm_order_id={order.crm_order_id}")
                        else:
                            print(f"❌ ERROR: payment_processed sigue siendo False para orden crm_order_id={order.crm_order_id}")
                except Exception as verify_error:
                    import traceback
                    print(f"⚠️  Error al verificar payment_processed: {str(verify_error)}")
                    print(traceback.format_exc())
            
            return success_response(
                data={},
                message="Datos sincronizados correctamente"
            )
            
        except Exception as e:
            db.session.rollback()
            import traceback
            print(f"[DEBUG] Excepcion en /public/sincronizar: {str(e)}")
            print(traceback.format_exc())
            return processing_error(f"Error al sincronizar datos: {str(e)}")
            
    except Exception as e:
        import traceback
        print(f"[DEBUG] Excepcion (server) en /public/sincronizar: {str(e)}")
        print(traceback.format_exc())
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


@public_api_bp.route('/api/ventas/sincronizar', methods=['POST'])
@api_key_required
def sincronizar_datos():
    """
    Endpoint para sincronizar datos del CRM.
    
    Puede funcionar de dos formas:
    1. CONSULTA: Devuelve datos del CRM cuando se envía solo 'tipo' (y opcionalmente 'id' o 'fecha')
    2. NOTIFICACIÓN: Recibe notificaciones de cambios cuando se envía 'datos' y 'sincronizar'
    
    Request Body (Consulta):
    {
        "tipo": "stock" | "productos" | "zonas" | "provincias" | "tipos_documento" | "tipos_venta" | "ventas",
        "id": 123 (opcional),
        "fecha": "2024-01-15 10:30:00" (opcional, ignorado para stock)
    }
    
    Request Body (Notificación):
    {
        "tipo": "stock" | "productos" | "zonas" | ...,
        "datos": [...],
        "status": true,
        "filtros": {...},
        "sincronizar": {
            "accion": "update" | "create" | "delete",
            "timestamp": "2026-01-02 15:20:50"
        }
    }
    
    Response - Éxito (Consulta):
    HTTP Status: 200 OK
    {
        "status": true,
        "tipo": "stock",
        "filtros": {"id": 0},
        "datos": [
            {
                "id": 26,
                "descripcion": "Base ecocuero 070 x 190",
                "estado": "habilitado",
                "combo": false
            }
        ],
        "sincronizar": {
            "accion": "sincronizar",
            "timestamp": "2024-01-15 10:30:00"
        }
    }
    
    Response - Error 404:
    HTTP Status: 404 Not Found
    {
        "status": false,
        "message": "El ID 999 no existe para el tipo stock",
        "tipo": "stock",
        "filtros": {"id": 999},
        "datos": []
    }
    """
    try:
        # Obtener datos del body
        data = request.get_json() or {}
        
        tipo = data.get('tipo')
        if not tipo:
            return jsonify({
                "status": False,
                "message": "El campo 'tipo' es requerido"
            }), 422
        
        # Verificar si es una consulta o una notificación
        tiene_datos = 'datos' in data and data.get('datos') is not None
        tiene_sincronizar = 'sincronizar' in data and data.get('sincronizar') is not None
        
        # Si tiene datos y sincronizar, es una notificación -> redirigir a /public/sincronizar
        if tiene_datos and tiene_sincronizar:
            # Es una notificación, procesar en el endpoint de sincronización
            # Por ahora, para stock solo aceptamos notificaciones sin procesar
            if tipo == 'stock':
                return success_response(
                    data={},
                    message="Notificación de stock recibida correctamente"
                )
            else:
                # Para otros tipos, redirigir al endpoint de sincronización
                # (esto se puede hacer llamando a la función directamente)
                return sync_data_new()
        
        # Es una consulta - devolver datos según el tipo
        registro_id = data.get('id')
        fecha = data.get('fecha')
        
        # Construir filtros para la respuesta
        filtros = {}
        if registro_id:
            filtros['id'] = registro_id
        elif fecha:
            filtros['fecha'] = fecha
        
        # Procesar según el tipo
        if tipo == 'stock':
            # Obtener stock del CRM
            try:
                productos_stock = obtener_stock_crm(registro_id=registro_id)
            except Exception as e:
                import traceback
                return jsonify({
                    "status": False,
                    "message": "Error al procesar la sincronización",
                    "error": str(e) if Config.DEBUG_MODE else None,
                    "traceback": traceback.format_exc() if Config.DEBUG_MODE else None
                }), 500
            
            # Si se solicitó un ID específico y no se encontró
            if registro_id and len(productos_stock) == 0:
                return jsonify({
                    "status": False,
                    "message": f"El ID {registro_id} no existe para el tipo stock",
                    "tipo": "stock",
                    "filtros": filtros,
                    "datos": []
                }), 404
            
            # Generar timestamp
            from datetime import datetime
            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            
            return jsonify({
                "status": True,
                "tipo": "stock",
                "filtros": filtros if filtros else {"id": 0},
                "datos": productos_stock,
                "sincronizar": {
                    "accion": "sincronizar",
                    "timestamp": timestamp
                }
            }), 200
        
        else:
            # Para otros tipos, devolver error (aún no implementado)
            return jsonify({
                "status": False,
                "message": f"Consulta de tipo '{tipo}' no implementada en este endpoint. Use /api/ventas/lista para ventas."
            }), 501
        
    except Exception as e:
        import traceback
        return jsonify({
            "status": False,
            "message": "Error al procesar la sincronización",
            "error": str(e) if Config.DEBUG_MODE else None,
            "traceback": traceback.format_exc() if Config.DEBUG_MODE else None
        }), 500


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


def obtener_stock_crm(registro_id=None):
    """
    Obtiene el estado de stock de productos del CRM.
    
    El estado se calcula comparando stock > limite_minimo:
    - Si stock > limite_minimo: estado = "habilitado"
    - Si stock <= limite_minimo: estado = "inhabilitado"
    
    Para combos, el estado depende de que todos sus componentes tengan suficiente stock.
    
    Args:
        registro_id: ID específico del producto (opcional). Si se proporciona, devuelve solo ese producto.
    
    Returns:
        Lista de productos con su estado de stock:
        [
            {
                "id": 26,
                "descripcion": "Base ecocuero 070 x 190",
                "estado": "habilitado",
                "combo": false
            },
            ...
        ]
    """
    from sqlalchemy import text
    
    # Query base para obtener productos con su stock
    # Nota: El campo stock es boolean, no integer
    query = """
        SELECT 
            cp.crm_product_id as id,
            cp.description as descripcion,
            cp.combo,
            COALESCE(cp.stock, false) as stock,
            COALESCE(cp.min_limit, 0) as limite_minimo
        FROM crm_products cp
        WHERE 1=1
    """
    
    params = {}
    
    # Si se proporciona un ID específico, filtrar por ese ID
    if registro_id:
        query += " AND cp.crm_product_id = :id"
        params['id'] = registro_id
    
    # Ordenar por ID
    query += " ORDER BY cp.crm_product_id"
    
    try:
        result = db.session.execute(text(query), params)
        rows = result.fetchall()
    except Exception as e:
        import traceback
        raise Exception(f"Error al consultar stock del CRM: {str(e)}")
    
    productos_stock = []
    
    for row in rows:
        producto_id = row.id
        descripcion = row.descripcion or ""
        combo = bool(row.combo) if row.combo is not None else False
        # El campo stock es boolean
        stock_boolean = bool(row.stock) if row.stock is not None else False
        
        # Calcular estado: habilitado si stock = true
        estado = "habilitado" if stock_boolean else "inhabilitado"
        
        # Si es combo, verificar que todos los componentes tengan suficiente stock
        if combo:
            # Consultar componentes del combo
            query_combo = """
                SELECT 
                    cpci.crm_item_product_id,
                    COALESCE(cp2.stock, false) as item_stock
                FROM crm_combo_items cpci
                INNER JOIN crm_products cp2 ON cp2.crm_product_id = cpci.crm_item_product_id
                WHERE cpci.crm_combo_product_id = :combo_id
            """
            
            try:
                combo_result = db.session.execute(
                    text(query_combo),
                    {'combo_id': producto_id}
                )
                combo_rows = combo_result.fetchall()
                
                # Verificar que todos los componentes tengan stock (stock = true)
                todos_habilitados = True
                for combo_row in combo_rows:
                    item_stock = bool(combo_row.item_stock) if combo_row.item_stock is not None else False
                    if not item_stock:
                        todos_habilitados = False
                        break
                
                estado = "habilitado" if todos_habilitados else "inhabilitado"
            except Exception as e:
                # Si hay error al consultar componentes, usar el estado del combo principal
                pass
        
        productos_stock.append({
            'id': producto_id,
            'descripcion': descripcion,
            'estado': estado,
            'combo': combo
        })
    
    return productos_stock


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
    Valida el formato del CUIT.
    Acepta formato con guiones (XX-XXXXXXXX-X) o sin guiones (11 dígitos).
    Si viene sin guiones, lo formatea automáticamente.
    Retorna: (es_valido, mensaje_error, cuit_formateado)
    """
    if not cuit:
        return False, "El CUIT no puede estar vacío", None
    
    # Convertir a string y limpiar espacios
    cuit = str(cuit).strip()
    
    # Remover guiones y espacios para normalizar
    cuit_limpio = cuit.replace('-', '').replace(' ', '')
    
    # Validar que tenga exactamente 11 dígitos
    if not cuit_limpio.isdigit():
        return False, "El CUIT debe contener solo números", None
    
    if len(cuit_limpio) != 11:
        return False, f"El CUIT debe tener 11 dígitos (tiene {len(cuit_limpio)})", None
    
    # Formatear con guiones: XX-XXXXXXXX-X
    cuit_formateado = f"{cuit_limpio[:2]}-{cuit_limpio[2:10]}-{cuit_limpio[10]}"
    
    return True, None, cuit_formateado


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
        from sqlalchemy.exc import IntegrityError
        from datetime import datetime, timezone, timedelta
        import re
        
        # Función helper para obtener la hora de Argentina (UTC-3)
        def get_argentina_time():
            """Retorna la fecha y hora actual en zona horaria de Argentina (UTC-3) como datetime naive"""
            argentina_tz = timezone(timedelta(hours=-3))
            return datetime.now(argentina_tz).replace(tzinfo=None)
        
        # ========================================================================
        # VALIDACIONES DE CAMPOS REQUERIDOS
        # ========================================================================
        print(f"[DEBUG crear_venta] Validando campos requeridos...")
        print(f"[DEBUG crear_venta] Data recibida: {json.dumps(data, indent=2, default=str)}")
        
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
            valor = data.get(campo)
            if campo not in data or valor is None or (isinstance(valor, str) and not valor.strip()):
                print(f"[DEBUG crear_venta] ❌ Campo faltante o vacío: {campo}, valor: {valor}, tipo: {type(valor)}")
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
        
        print(f"[DEBUG crear_venta] Validando documento: tipo_documento={tipo_documento}, documento_cliente='{documento_cliente}'")
        
        if tipo_documento == 1:  # DNI
            # Validar formato DNI (solo números)
            if documento_cliente:
                # Remover guiones y espacios para validar
                documento_limpio = documento_cliente.replace('-', '').replace(' ', '')
                if not documento_limpio.isdigit():
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
            
            es_valido, mensaje_error, documento_formateado = validar_cuit(documento_cliente)
            if not es_valido:
                return jsonify({
                    "status": False,
                    "message": mensaje_error
                }), 422
            
            # Usar el documento formateado (con guiones) si se normalizó
            if documento_formateado:
                documento_cliente = documento_formateado
                data['documento_cliente'] = documento_formateado
                print(f"[DEBUG crear_venta] CUIT formateado: '{documento_cliente}' -> '{documento_formateado}'")
        
        # ========================================================================
        # NORMALIZACIÓN DE TELÉFONO
        # ========================================================================
        def normalize_phone(phone_str):
            """Normaliza el teléfono: quita 0, 15, 150 al inicio y valida formato"""
            if not phone_str:
                return "3510000000"  # Teléfono por defecto
            
            # Convertir a string y limpiar espacios
            phone_str = str(phone_str).strip()
            
            # Remover caracteres no numéricos (excepto + al inicio)
            phone_cleaned = ''.join(c for c in phone_str if c.isdigit())
            
            # Quitar prefijos comunes
            if phone_cleaned.startswith('0'):
                phone_cleaned = phone_cleaned[1:]
            elif phone_cleaned.startswith('150'):
                phone_cleaned = phone_cleaned[3:]
            elif phone_cleaned.startswith('15'):
                phone_cleaned = phone_cleaned[2:]
            
            # Validar formato: debe tener entre 8 y 11 dígitos (código de área + número)
            if len(phone_cleaned) < 8 or len(phone_cleaned) > 11:
                print(f"[DEBUG crear_venta] Teléfono no tiene formato válido (longitud: {len(phone_cleaned)}), usando default: 3510000000")
                return "3510000000"
            
            # Verificar que sean solo dígitos
            if not phone_cleaned.isdigit():
                print(f"[DEBUG crear_venta] Teléfono contiene caracteres no numéricos, usando default: 3510000000")
                return "3510000000"
            
            return phone_cleaned
        
        # Normalizar teléfono del cliente
        cliente_telefono_original = data.get('cliente_telefono', '')
        data['cliente_telefono'] = normalize_phone(cliente_telefono_original)
        if cliente_telefono_original != data['cliente_telefono']:
            print(f"[DEBUG crear_venta] Teléfono normalizado: '{cliente_telefono_original}' -> '{data['cliente_telefono']}'")
        
        # Normalizar teléfono alternativo si existe
        if 'cel_alternativo' in data and data.get('cel_alternativo'):
            cel_alternativo_original = data.get('cel_alternativo', '')
            data['cel_alternativo'] = normalize_phone(cel_alternativo_original)
            if cel_alternativo_original != data['cel_alternativo']:
                print(f"[DEBUG crear_venta] Teléfono alternativo normalizado: '{cel_alternativo_original}' -> '{data['cel_alternativo']}'")
        
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
            
            # Calcular el subtotal del renglón
            # IMPORTANTE: 'precio' ya es el precio TOTAL (precio unitario * cantidad)
            # según la documentación del endpoint externo
            subtotal_renglon = float(precio)  # precio ya incluye cantidad
            total_venta += subtotal_renglon
        
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
        
        # Obtener descuento de billetera si existe
        used_wallet_amount = data.get('used_wallet_amount') or data.get('wallet_amount') or 0.0
        if used_wallet_amount:
            try:
                used_wallet_amount = float(used_wallet_amount)
            except (ValueError, TypeError):
                used_wallet_amount = 0.0
        
        # IMPORTANTE: Si hay descuento de billetera, los precios en 'js' ya vienen ajustados
        # (con el descuento aplicado proporcionalmente). Por lo tanto, total_venta ya es
        # el total después del descuento. No debemos restar el descuento de nuevo.
        # Si NO hay descuento, total_venta es el total original.
        # En ambos casos, validamos que total_pagos == total_venta
        
        # Validar que la suma de pagos coincida con el total de la venta
        # (que ya incluye el descuento si fue aplicado en los precios)
        diferencia = abs(total_pagos - total_venta)
        if diferencia > 0.01:  # Tolerancia de 1 centavo
            return jsonify({
                "status": False,
                "message": "La suma de los pagos no coincide con el total de la venta",
                "total_productos": total_venta,  # Este ya es el total después del descuento si aplica
                "descuento_billetera": used_wallet_amount,
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
            
            # Parsear fecha_detalle - debe venir en formato 'YYYY-MM-DD' desde orders.py
            # Si no viene o está vacía, usar la fecha actual de Argentina
            if data.get('fecha_detalle'):
                try:
                    fecha_detalle = datetime.strptime(data['fecha_detalle'], '%Y-%m-%d').date()
                    print(f"[DEBUG crear_venta] fecha_detalle recibida: {fecha_detalle}")
                except Exception as e:
                    print(f"[DEBUG crear_venta] ⚠️ Error al parsear fecha_detalle '{data.get('fecha_detalle')}': {str(e)}, usando fecha actual de Argentina")
                    fecha_detalle = get_argentina_time().date()
            else:
                print(f"[DEBUG crear_venta] ⚠️ fecha_detalle no recibida, usando fecha actual de Argentina")
                fecha_detalle = get_argentina_time().date()
            
            print(f"[DEBUG crear_venta] fecha_detalle final: {fecha_detalle}")
            
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
            
            # ====================================================================
            # LLAMAR AL ENDPOINT EXTERNO PRIMERO PARA OBTENER EL crm_order_id
            # ====================================================================
            external_response_info = None
            external_venta_id = None  # ID que retorna el endpoint externo
            external_numero_comprobante = None  # numero_comprobante que retorna el endpoint externo
            
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
                        es_valido, mensaje_error, documento_formateado = validar_cuit(payload_externo['documento_cliente'])
                        if not es_valido:
                            print(f"ADVERTENCIA: CUIT aún inválido después de normalizar: {payload_externo['documento_cliente']}")
                            print(f"Error: {mensaje_error}")
                        elif documento_formateado:
                            # Actualizar el payload con el CUIT formateado
                            payload_externo['documento_cliente'] = documento_formateado
                            print(f"[DEBUG sincronizar_datos] CUIT formateado en payload externo: '{documento_formateado}'")
                    
                    # Construir el array js con la estructura exacta esperada
                    # IMPORTANTE: El campo "precio" en data['js'] ya es el precio TOTAL (precio unitario * cantidad)
                    # según la documentación del endpoint externo
                    js_array = []
                    for renglon in data.get('js', []):
                        if renglon.get('accion') == 'N':
                            cantidad = float(renglon.get('cantidad_recibida', 0))
                            # 'precio' ya es el precio TOTAL, no el unitario
                            precio_total = float(renglon.get('precio', 0))
                            unitario_sin_fpago = float(renglon.get('unitario_sin_fpago', 0))
                            
                            # Si unitario_sin_fpago no está presente, calcularlo dividiendo el total por la cantidad
                            if unitario_sin_fpago <= 0 and cantidad > 0:
                                unitario_sin_fpago = precio_total / cantidad
                            
                            js_item = {
                                "id": None,
                                "accion": "N",
                                "item_id": renglon.get('item_id'),
                                "cantidad_recibida": cantidad,
                                "precio": precio_total,  # Precio TOTAL del producto (ya viene calculado)
                                "unitario_sin_fpago": unitario_sin_fpago,
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
                    
                    # Agregar el total calculado (el endpoint externo no calcula, necesita recibirlo)
                    payload_externo["total"] = total_venta
                    
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
                    
                    # Debug: Verificar items y totales
                    if payload_externo.get('js'):
                        # IMPORTANTE: 'precio' ya es el precio TOTAL (precio unitario * cantidad)
                        total_calculado = sum(float(item.get('precio', 0)) for item in payload_externo['js'])
                        print(f"DEBUG: Total calculado de items (suma de precios totales): {total_calculado}")
                        print(f"DEBUG: Items enviados: {json.dumps(payload_externo['js'], indent=2, default=str)}")
                    if payload_externo.get('formaPagos'):
                        total_pagos = sum(float(pago.get('monto_total', 0)) for pago in payload_externo['formaPagos'])
                        print(f"DEBUG: Total de pagos: {total_pagos}")
                        print(f"DEBUG: FormaPagos enviados: {json.dumps(payload_externo['formaPagos'], indent=2, default=str)}")
                    
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
                        
                        # Extraer el venta_id y numero_comprobante de la respuesta del endpoint externo
                        if response_json:
                            print(f"[DEBUG crear_venta] response_json recibido: {json.dumps(response_json, indent=2, default=str)}")
                            
                            # Intentar obtener venta_id desde el root del JSON
                            external_venta_id = response_json.get('venta_id')
                            
                            # Si no está en el root, intentar desde data
                            if not external_venta_id and 'data' in response_json:
                                external_venta_id = response_json.get('data', {}).get('venta_id') or response_json.get('data', {}).get('crm_order_id')
                            
                            # Extraer numero_comprobante desde el root del JSON
                            external_numero_comprobante = response_json.get('numero_comprobante')
                            print(f"[DEBUG crear_venta] numero_comprobante extraído del root: {external_numero_comprobante}")
                            
                            # Si no está en el root, intentar desde data
                            if not external_numero_comprobante and 'data' in response_json:
                                external_numero_comprobante = response_json.get('data', {}).get('numero_comprobante')
                                print(f"[DEBUG crear_venta] numero_comprobante extraído de data: {external_numero_comprobante}")
                            
                            if external_venta_id:
                                print(f"INFO: El endpoint externo retornó venta_id: {external_venta_id}")
                                if external_numero_comprobante:
                                    print(f"INFO: El endpoint externo retornó numero_comprobante: {external_numero_comprobante}")
                                else:
                                    print(f"ADVERTENCIA: No se pudo extraer numero_comprobante de la respuesta del endpoint externo")
                                    print(f"[DEBUG crear_venta] Claves disponibles en response_json: {list(response_json.keys())}")
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
            
            # Si el endpoint externo no retornó un venta_id, retornar error
            if not external_venta_id:
                error_msg = "No se pudo obtener el ID de venta del endpoint externo"
                if external_response_info and external_response_info.get('error'):
                    error_msg = f"{error_msg}: {external_response_info.get('error')}"
                return jsonify({
                    "status": False,
                    "message": error_msg,
                    "data": {
                        "external_api": external_response_info
                    }
                }), 400
            
            # Usar el venta_id del endpoint externo como crm_order_id
            crm_order_id = external_venta_id
            print(f"[DEBUG crear_venta] ✅ Usando crm_order_id={crm_order_id} del endpoint externo")
            
            # Usar el numero_comprobante del endpoint externo si está disponible, sino usar el calculado localmente
            numero_comprobante_anterior = numero_comprobante  # Guardar el valor anterior para el log
            if external_numero_comprobante:
                numero_comprobante = external_numero_comprobante
                print(f"[DEBUG crear_venta] ✅ Usando numero_comprobante={numero_comprobante} del endpoint externo (valor anterior era: {numero_comprobante_anterior})")
            else:
                print(f"[DEBUG crear_venta] ⚠️ No se recibió numero_comprobante del endpoint externo, usando el calculado localmente: {numero_comprobante}")
                print(f"[DEBUG crear_venta] external_numero_comprobante es: {external_numero_comprobante}")
            
            # Generar UUID para el campo id
            nuevo_uuid = uuid.uuid4()
            
            # Insertar en crm_orders usando el crm_order_id del endpoint externo
            # Si ya existe, actualizar el registro existente
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
                    :crm_created_at, :crm_updated_at, CAST(:raw AS jsonb)
                )
                ON CONFLICT (crm_order_id) 
                DO UPDATE SET
                    receipt_number = EXCLUDED.receipt_number,
                    detail_date = EXCLUDED.detail_date,
                    crm_seller_id = EXCLUDED.crm_seller_id,
                    crm_sale_type_id = EXCLUDED.crm_sale_type_id,
                    client_name = EXCLUDED.client_name,
                    client_address = EXCLUDED.client_address,
                    client_phone = EXCLUDED.client_phone,
                    client_email = EXCLUDED.client_email,
                    client_document = EXCLUDED.client_document,
                    crm_doc_type_id = EXCLUDED.crm_doc_type_id,
                    crm_province_id = EXCLUDED.crm_province_id,
                    city = EXCLUDED.city,
                    crm_zone_id = EXCLUDED.crm_zone_id,
                    status = EXCLUDED.status,
                    total_sale = EXCLUDED.total_sale,
                    total_with_payment = EXCLUDED.total_with_payment,
                    is_cancelled = EXCLUDED.is_cancelled,
                    crm_updated_at = EXCLUDED.crm_updated_at,
                    raw = EXCLUDED.raw
                RETURNING crm_order_id
            """
            
            try:
                # Obtener hora de Argentina para crm_created_at y crm_updated_at
                now_argentina = get_argentina_time()
                
                insert_params = {
                    'id': str(nuevo_uuid),
                    'crm_order_id': crm_order_id,
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
                    'crm_created_at': now_argentina,
                    'crm_updated_at': now_argentina,
                    'raw': json.dumps(raw_data)
                }
                
                print(f"[DEBUG crear_venta] Insertando/actualizando en crm_orders con parámetros: {json.dumps({k: v for k, v in insert_params.items() if k != 'raw'}, indent=2, default=str)}")
                print(f"[DEBUG crear_venta] 🔍 VALOR DE receipt_number ANTES DEL INSERT: {insert_params.get('receipt_number')}")
                
                result_order = db.session.execute(
                    text(insert_order),
                    insert_params
                )
                
                crm_order_id = result_order.fetchone()[0]
                print(f"[DEBUG crear_venta] ✅ Registro insertado/actualizado en crm_orders con crm_order_id={crm_order_id}")
                print(f"[DEBUG crear_venta] Parámetros insertados: client_name={insert_params.get('client_name')}, client_email={insert_params.get('client_email')}, client_address={insert_params.get('client_address')}, client_phone={insert_params.get('client_phone')}, crm_zone_id={insert_params.get('crm_zone_id')}, crm_province_id={insert_params.get('crm_province_id')}, city={insert_params.get('city')}, total_sale={insert_params.get('total_sale')}, crm_sale_type_id={insert_params.get('crm_sale_type_id')}, client_document={insert_params.get('client_document')}, crm_doc_type_id={insert_params.get('crm_doc_type_id')}, receipt_number={insert_params.get('receipt_number')}")
            except Exception as e:
                # Si falla el INSERT de crm_orders, hacer rollback y retornar error
                db.session.rollback()
                error_msg = str(e)
                # Verificar si es un error de unique constraint (aunque debería ser manejado por ON CONFLICT)
                if 'UniqueViolation' in error_msg or 'duplicate key' in error_msg.lower():
                    print(f"[DEBUG crear_venta] ⚠️ Error de clave duplicada (debería ser manejado por ON CONFLICT): {error_msg}")
                    # Si aún así ocurre un error de duplicado para crm_order_id, el registro ya existe
                    # y podemos continuar con el flujo usando el crm_order_id existente
                    if 'crm_order_id' in error_msg:
                        print(f"[DEBUG crear_venta] ✅ Orden con crm_order_id={crm_order_id} ya existe, continuando con el flujo...")
                        # Continuar con el flujo - no hacer raise
                    else:
                        # Es un error de duplicado en otro campo, retornar error
                        return jsonify({
                            "status": False,
                            "message": f"Error de clave duplicada: {error_msg}"
                        }), 400
                # Verificar si es un error de foreign key para dar mensaje más específico
                elif 'ForeignKeyViolation' in error_msg or 'foreign key' in error_msg.lower():
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
                    else:
                        # Error de foreign key genérico
                        return jsonify({
                            "status": False,
                            "message": f"Error de referencia: {error_msg}"
                        }), 400
                else:
                    # Error genérico
                    print(f"[DEBUG crear_venta] ⚠️ Error inesperado al insertar/actualizar crm_orders: {error_msg}")
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
            print(f"[DEBUG crear_venta] Haciendo commit de la transacción...")
            db.session.commit()
            print(f"[DEBUG crear_venta] ✅ Commit exitoso. crm_order_id={crm_order_id}")
            
            # Verificar que el receipt_number se guardó correctamente
            verify_query = text("SELECT receipt_number FROM crm_orders WHERE crm_order_id = :crm_order_id")
            verify_result = db.session.execute(verify_query, {'crm_order_id': crm_order_id})
            verify_row = verify_result.fetchone()
            if verify_row:
                saved_receipt_number = verify_row[0]
                print(f"[DEBUG crear_venta] 🔍 VERIFICACIÓN POST-COMMIT: receipt_number guardado en BD: {saved_receipt_number}")
                if saved_receipt_number != numero_comprobante:
                    print(f"[DEBUG crear_venta] ⚠️ ADVERTENCIA: El receipt_number guardado ({saved_receipt_number}) no coincide con el esperado ({numero_comprobante})")
                else:
                    print(f"[DEBUG crear_venta] ✅ El receipt_number se guardó correctamente: {saved_receipt_number}")
            else:
                print(f"[DEBUG crear_venta] ⚠️ ADVERTENCIA: No se encontró el registro en crm_orders después del commit")
            
            # Verificar que los datos se guardaron correctamente
            try:
                verify_query = text("""
                    SELECT client_name, client_email, client_address, client_phone, 
                           crm_zone_id, crm_province_id, city, total_sale, crm_sale_type_id,
                           client_document, crm_doc_type_id, receipt_number
                    FROM crm_orders 
                    WHERE crm_order_id = :crm_order_id
                """)
                verify_result = db.session.execute(verify_query, {'crm_order_id': crm_order_id})
                verify_row = verify_result.fetchone()
                if verify_row:
                    print(f"[DEBUG crear_venta] ✅ Verificación post-commit: client_name={verify_row[0]}, client_email={verify_row[1]}, client_address={verify_row[2]}, client_phone={verify_row[3]}, crm_zone_id={verify_row[4]}, crm_province_id={verify_row[5]}, city={verify_row[6]}, total_sale={verify_row[7]}, crm_sale_type_id={verify_row[8]}, receipt_number={verify_row[11]}")
                else:
                    print(f"[DEBUG crear_venta] ⚠️ No se encontró registro después del commit con crm_order_id={crm_order_id}")
            except Exception as verify_error:
                print(f"[DEBUG crear_venta] Error al verificar después del commit: {str(verify_error)}")
            
            # NOTA: No llamamos a sync_crm_ventas aquí porque los datos ya fueron
            # insertados directamente en crm_orders. Llamar a sync_crm_ventas con datos
            # mínimos (solo id y estado) sobreescribía la fila y borraba campos como
            # receipt_number, client_name, etc.
            
            # ====================================================================
            # PREPARAR RESPUESTA Y MANEJAR ERRORES
            # ====================================================================
            # El endpoint externo ya fue llamado al principio, ahora solo manejamos la respuesta
            mensaje_respuesta = "Venta creada exitosamente"
            endpoint_externo_fallo = False
            mensaje_error_externo = None
            es_error_stock = False  # Flag para detectar error de stock
            
            # Verificar si hubo errores en la llamada al endpoint externo
            if external_response_info and not external_response_info.get('success'):
                response_json = external_response_info.get('response_json')
                if isinstance(response_json, dict):
                    mensaje_error_externo = response_json.get('message') or external_response_info.get('error')
                    # Detectar si es error de stock (precio de compra)
                    if mensaje_error_externo and ("No se pudo obtener el precio de compra" in mensaje_error_externo or "compras previas registradas" in mensaje_error_externo):
                        es_error_stock = True
                        mensaje_error_externo = "Lo sentimos, pero este artículo no tiene stock."
                else:
                    mensaje_error_externo = external_response_info.get('error')
                if mensaje_error_externo and not es_error_stock:
                    mensaje_respuesta = f"Venta creada localmente, pero falló en endpoint externo: {mensaje_error_externo}"
                    endpoint_externo_fallo = True
            
            # Si es error de stock, retornar error sin crear nada (el endpoint externo ya fue llamado)
            if es_error_stock:
                print(f"[DEBUG crear_venta] ⚠️ Error de stock detectado, no se creará la venta")
                return jsonify({
                    "status": False,
                    "message": mensaje_error_externo,
                    "data": {
                        "external_api": external_response_info
                    }
                }), 400
            
            # Crear la orden en la tabla orders si se recibió user_id
            # Solo crear la orden si la venta se creó exitosamente (antes de llamar al endpoint externo)
            order_id = None
            if data.get('user_id'):
                try:
                    from models.order import Order
                    from models.order_item import OrderItem
                    import uuid as uuid_lib
                    
                    user_id = uuid_lib.UUID(data['user_id']) if isinstance(data['user_id'], str) else data['user_id']
                    
                    # Obtener datos adicionales para la orden
                    payment_method = data.get('payment_method', 'card')
                    payment_processed = data.get('payment_processed', False)
                    used_wallet_amount = data.get('used_wallet_amount')
                    
                    # Verificar si ya existe una orden con este crm_order_id
                    existing_order = Order.query.filter_by(crm_order_id=crm_order_id).first()
                    if existing_order:
                        # Actualizar la orden existente
                        existing_order.user_id = user_id
                        existing_order.total = total_venta
                        existing_order.payment_method = payment_method
                        existing_order.crm_sale_type_id = data.get('tipo_venta')
                        existing_order.used_wallet_amount = float(used_wallet_amount) if used_wallet_amount else None
                        # Actualizar referral_code_used si viene en el payload
                        if data.get('referral_code_used'):
                            existing_order.referral_code_used = data.get('referral_code_used', '').strip().upper()
                        # Actualizar payment_processed (importante: hacerlo al final para procesar referido)
                        was_paid = existing_order.payment_processed
                        existing_order.payment_processed = payment_processed
                        
                        # Si la orden tiene un created_at muy antiguo o parece estar en UTC (diferencia > 2 horas),
                        # actualizarlo a la hora de Argentina
                        from datetime import datetime, timezone, timedelta
                        def get_argentina_time():
                            argentina_tz = timezone(timedelta(hours=-3))
                            return datetime.now(argentina_tz).replace(tzinfo=None)
                        
                        if existing_order.created_at:
                            # Calcular diferencia entre created_at y ahora (en horas)
                            now_argentina = get_argentina_time()
                            time_diff = abs((now_argentina - existing_order.created_at).total_seconds() / 3600)
                            # Si la diferencia es mayor a 2 horas, probablemente está en UTC, actualizar
                            if time_diff > 2:
                                existing_order.created_at = get_argentina_time()
                                print(f"[DEBUG crear_venta] ⚠️ Actualizado created_at de orden existente (parecía estar en UTC)")
                        
                        order = existing_order
                        order_id = str(order.id)
                        print(f"[DEBUG crear_venta] ✅ Orden existente actualizada con id={order_id}")
                        
                        # Procesar crédito de referido si la orden se marcó como pagada y tiene código de referido
                        if payment_processed and not was_paid and order.referral_code_used:
                            try:
                                from routes.referrals import process_referral_credit
                                process_referral_credit(order)
                                print(f"[DEBUG crear_venta] ✅ Procesado crédito de referido para orden existente {order_id}")
                            except Exception as referral_error:
                                import traceback
                                print(f"[DEBUG crear_venta] ⚠️ Error al procesar crédito de referido: {str(referral_error)}")
                                print(traceback.format_exc())
                    else:
                        # Crear la orden
                        referral_code_used = data.get('referral_code_used', '').strip().upper() if data.get('referral_code_used') else None
                        order = Order(
                            user_id=user_id,
                            crm_order_id=crm_order_id,
                            crm_sale_type_id=data.get('tipo_venta'),
                            total=total_venta,
                            status='pending',
                            payment_method=payment_method,
                            payment_processed=payment_processed,
                            used_wallet_amount=float(used_wallet_amount) if used_wallet_amount else None,
                            referral_code_used=referral_code_used
                        )
                        db.session.add(order)
                        db.session.flush()
                        order_id = str(order.id)
                        print(f"[DEBUG crear_venta] ✅ Orden creada en tabla orders con id={order_id} (antes de commit)")
                    
                    # Crear o actualizar los items de la orden
                    if data.get('order_items'):
                        # Eliminar items existentes si la orden ya existía
                        if existing_order:
                            OrderItem.query.filter_by(order_id=order.id).delete()
                        
                        for item_data in data['order_items']:
                            product_id = uuid_lib.UUID(item_data['product_id']) if isinstance(item_data['product_id'], str) else item_data['product_id']
                            variant_id = None
                            if item_data.get('variant_id'):
                                variant_id = uuid_lib.UUID(item_data['variant_id']) if isinstance(item_data['variant_id'], str) else item_data['variant_id']
                            
                            # Crear OrderItem
                            # Nota: variant_id no está disponible porque la columna no existe en la tabla
                            # Si necesitas variant_id, necesitas hacer una migración para agregar la columna
                            # La columna en la BD es unit_price, no price
                            order_item = OrderItem(
                                order_id=order.id,
                                product_id=product_id,
                                quantity=item_data.get('quantity', 1),
                                unit_price=float(item_data.get('price', 0))  # price en item_data es el precio unitario
                            )
                            db.session.add(order_item)
                    
                    db.session.commit()
                    # Refrescar la orden después del commit para asegurar que todos los datos estén actualizados
                    db.session.refresh(order)
                    order_id = str(order.id)  # Asegurar que tenemos el ID correcto después del commit
                    print(f"[DEBUG crear_venta] ✅ Orden guardada en BD con id={order_id}, total={order.total}, status={order.status}")
                    
                    # Procesar crédito de referido si la orden está pagada y tiene código de referido
                    if order.payment_processed and order.referral_code_used:
                        try:
                            from routes.referrals import process_referral_credit
                            process_referral_credit(order)
                            print(f"[DEBUG crear_venta] ✅ Procesado crédito de referido para orden {order_id}")
                        except Exception as referral_error:
                            # No fallar la creación de orden si falla el procesamiento de referido
                            import traceback
                            print(f"[DEBUG crear_venta] ⚠️ Error al procesar crédito de referido: {str(referral_error)}")
                            print(traceback.format_exc())
                except IntegrityError as integrity_error:
                    db.session.rollback()
                    # Si es un error de duplicado, intentar obtener la orden existente
                    if 'crm_order_id' in str(integrity_error):
                        existing_order = Order.query.filter_by(crm_order_id=crm_order_id).first()
                        if existing_order:
                            order_id = str(existing_order.id)
                            print(f"[DEBUG crear_venta] ✅ Orden ya existía, usando orden con id={order_id}")
                        else:
                            raise
                    else:
                        raise
                except Exception as order_error:
                    db.session.rollback()
                    import traceback
                    print(f"[DEBUG crear_venta] ⚠️ Error al crear orden en tabla orders: {str(order_error)}")
                    print(traceback.format_exc())
                    # No fallar la creación de la venta si falla la creación de la orden
            
            # Si el endpoint externo falló, guardar en la tabla de reintentos
            if endpoint_externo_fallo:
                try:
                    from models.sale_retry_queue import SaleRetryQueue
                    import uuid as uuid_lib
                    from datetime import datetime as dt
                    
                    # Extraer campos del payload para facilitar consultas
                    fecha_detalle = None
                    if payload_original and payload_original.get('fecha_detalle'):
                        try:
                            fecha_detalle = dt.strptime(payload_original['fecha_detalle'], '%Y-%m-%d').date()
                        except:
                            pass
                    
                    # Obtener user_id si está disponible
                    user_id_uuid = None
                    if payload_original and payload_original.get('user_id'):
                        try:
                            user_id_uuid = uuid_lib.UUID(payload_original['user_id']) if isinstance(payload_original['user_id'], str) else payload_original['user_id']
                        except:
                            pass
                    
                    # Obtener order_id si ya se creó la orden
                    order_id_uuid = None
                    if order_id:
                        try:
                            order_id_uuid = uuid_lib.UUID(order_id) if isinstance(order_id, str) else order_id
                        except:
                            pass
                    
                    # Calcular monto_total desde formaPagos
                    monto_total = None
                    if payload_original and payload_original.get('formaPagos'):
                        forma_pagos = payload_original['formaPagos']
                        if isinstance(forma_pagos, list) and len(forma_pagos) > 0:
                            monto_total = forma_pagos[0].get('monto_total')
                    
                    # Crear registro en sale_retry_queue
                    retry_record = SaleRetryQueue(
                        order_id=order_id_uuid,
                        status='pending',
                        retry_count=0,
                        max_retries=5,
                        error_message=mensaje_error_externo,
                        error_details=external_response_info,
                        crm_payload=payload_original,
                        fecha_detalle=fecha_detalle,
                        tipo_venta=payload_original.get('tipo_venta') if payload_original else None,
                        cliente_nombre=payload_original.get('cliente_nombre') if payload_original else None,
                        cliente_email=payload_original.get('email_cliente') if payload_original else None,
                        provincia_id=payload_original.get('provincia_id') if payload_original else None,
                        zona_id=payload_original.get('zona_id') if payload_original else None,
                        monto_total=monto_total,
                        payment_method=payload_original.get('payment_method') if payload_original else None,
                        payment_processed=payload_original.get('payment_processed') if payload_original else None,
                        user_id=user_id_uuid,
                        priority=0
                    )
                    db.session.add(retry_record)
                    db.session.commit()
                    print(f"[DEBUG crear_venta] ✅ Venta guardada en sale_retry_queue con id={retry_record.id} debido a fallo en endpoint externo")
                except Exception as retry_error:
                    db.session.rollback()
                    import traceback
                    print(f"[DEBUG crear_venta] ⚠️ Error al guardar en sale_retry_queue: {str(retry_error)}")
                    print(traceback.format_exc())
                    # No fallar la creación de la venta si falla el guardado en la cola de reintentos
            
            response_data = {
                "crm_order_id": crm_order_id,
                "numero_comprobante": numero_comprobante
            }
            
            if order_id:
                response_data["order_id"] = order_id
            
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


@public_api_bp.route('/public/wallet/expiring-balance-reminders', methods=['POST'])
@api_key_required
def send_wallet_expiring_balance_reminders():
    """
    Endpoint para ser llamado mediante cron job que revisa usuarios con saldo próximo a vencer
    en la billetera y les envía un email de aviso.
    
    Requiere API key en header: X-API-Key o Authorization: Bearer <key>
    
    Request Body (opcional):
    {
        "days_ahead": 7  // Días por adelantado para considerar saldo próximo a vencer (default: 7)
    }
    
    Response - Éxito:
    HTTP Status: 200 OK
    {
        "status": true,
        "data": {
            "sent_count": 5,
            "failed_count": 0,
            "total_users": 5
        },
        "message": "Se enviaron 5 recordatorios exitosamente"
    }
    
    Response - Error:
    HTTP Status: 200 (con status: false) o 500
    {
        "status": false,
        "message": "Error al procesar los recordatorios: [descripción]"
    }
    """
    try:
        # Obtener días por adelantado desde el body (default: 7 días)
        data = request.get_json() or {}
        days_ahead = data.get('days_ahead', 7)
        
        try:
            days_ahead = int(days_ahead)
            if days_ahead < 1:
                return validation_error("days_ahead debe ser un número positivo")
        except (ValueError, TypeError):
            return validation_error("days_ahead debe ser un número válido")
        
        # Calcular fecha límite
        now = datetime.utcnow()
        expiration_limit = now + timedelta(days=days_ahead)
        
        # Tipos de movimientos de crédito (suman dinero)
        credit_types = ['manual_credit', 'cashback', 'refund', 'transfer_in', 'accreditation', 'credit']
        
        # Query para obtener usuarios con saldo próximo a vencer
        # Buscamos movimientos de crédito que:
        # 1. Tienen expires_at (no son None)
        # 2. Vencen entre ahora y days_ahead días
        # 3. Aún no han vencido (expires_at > now)
        # 4. Son movimientos de crédito (suman dinero)
        upcoming_expirations = db.session.query(
            User.id,
            User.email,
            User.first_name,
            User.last_name,
            func.sum(WalletMovement.amount).label('expiring_balance')
        ).join(
            Wallet, User.id == Wallet.user_id
        ).join(
            WalletMovement, Wallet.id == WalletMovement.wallet_id
        ).filter(
            and_(
                User.email.isnot(None),
                User.email != '',
                WalletMovement.type.in_(credit_types),
                WalletMovement.amount > 0,
                WalletMovement.expires_at.isnot(None),
                WalletMovement.expires_at > now,
                WalletMovement.expires_at <= expiration_limit
            )
        ).group_by(
            User.id, User.email, User.first_name, User.last_name
        ).having(
            func.sum(WalletMovement.amount) > 0
        ).all()
        
        if not upcoming_expirations:
            return success_response(
                data={
                    "sent_count": 0,
                    "failed_count": 0,
                    "total_users": 0
                },
                message="No hay usuarios con saldo próximo a vencer"
            )
        
        sent_count = 0
        failed_count = 0
        
        # Enviar recordatorio a cada usuario
        for user_id, email, first_name, last_name, expiring_balance in upcoming_expirations:
            try:
                # Formatear el saldo (convertir Decimal a float y formatear en formato argentino)
                balance_value = float(expiring_balance) if isinstance(expiring_balance, Decimal) else float(expiring_balance)
                # Formato argentino: $1.234,56
                balance_str = f"${balance_value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                
                # Obtener la fecha de vencimiento más próxima para este usuario
                earliest_expiration = db.session.query(
                    func.min(WalletMovement.expires_at)
                ).join(
                    Wallet, WalletMovement.wallet_id == Wallet.id
                ).filter(
                    and_(
                        Wallet.user_id == user_id,
                        WalletMovement.type.in_(credit_types),
                        WalletMovement.amount > 0,
                        WalletMovement.expires_at.isnot(None),
                        WalletMovement.expires_at > now,
                        WalletMovement.expires_at <= expiration_limit
                    )
                ).scalar()
                
                # Calcular días hasta el vencimiento
                if earliest_expiration:
                    days_until_expiry = (earliest_expiration - now).days
                    if days_until_expiry == 0:
                        expiry_text = "hoy"
                    elif days_until_expiry == 1:
                        expiry_text = "mañana"
                    else:
                        expiry_text = f"en {days_until_expiry} días"
                else:
                    expiry_text = "próximamente"
                
                # Crear el mensaje personalizado
                main_content = f"""
                <p>Tenés saldo en tu billetera Bausing que vence {expiry_text}.</p>
                <p><strong>Saldo próximo a vencer: {balance_str}</strong></p>
                <p>Te recomendamos que utilices tu saldo antes de que expire. Podés usarlo para realizar compras en nuestra tienda.</p>
                <p>¡No dejes que se venza tu saldo!</p>
                """
                
                # Enviar email
                success = email_service.send_custom_email(
                    to=email,
                    title="Recordatorio: Tu saldo de billetera vence pronto",
                    header_text="Recordatorio de Billetera",
                    greeting=f"Hola {first_name},",
                    main_content=main_content,
                    button_text="Ver mi billetera",
                    button_url=f"{Config.FRONTEND_URL}/billetera" if Config.FRONTEND_URL else None,
                    footer_note="Este es un recordatorio automático de Bausing."
                )
                
                if success:
                    sent_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                print(f"Error al enviar recordatorio a {email}: {str(e)}")
                import traceback
                print(traceback.format_exc())
                failed_count += 1
        
        return success_response(
            data={
                "sent_count": sent_count,
                "failed_count": failed_count,
                "total_users": len(upcoming_expirations)
            },
            message=f"Se enviaron {sent_count} recordatorios exitosamente"
        )
        
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"Error en send_wallet_expiring_balance_reminders: {str(e)}")
        print(f"Traceback completo:\n{error_traceback}")
        return server_error(f"Error al procesar los recordatorios: {str(e)}")


@public_api_bp.route('/public/sale-retry/process', methods=['POST'])
@api_key_required
def process_sale_retries():
    """
    Endpoint para ser llamado mediante cron job que procesa los reintentos de ventas pendientes
    en la tabla sale_retry_queue.
    
    Requiere API key en header: X-API-Key o Authorization: Bearer <key>
    
    Este endpoint:
    - Revisa las solicitudes de carga pendientes en sale_retry_queue
    - Omite las que han alcanzado max_retries intentos o status 'completed'
    - Envía el crm_payload al endpoint externo de carga de ventas
    - Actualiza last_retry_at y completed_at cuando corresponda
    - Actualiza la tabla orders con crm_order_id cuando corresponda
    
    Response - Éxito:
    HTTP Status: 200 OK
    {
        "status": true,
        "data": {
            "processed_count": 5,
            "successful_count": 4,
            "failed_count": 1,
            "skipped_count": 2
        },
        "message": "Se procesaron 5 reintentos exitosamente"
    }
    
    Response - Error:
    HTTP Status: 200 (con status: false) o 500
    {
        "status": false,
        "message": "Error al procesar los reintentos: [descripción]"
    }
    """
    try:
        from models.sale_retry_queue import SaleRetryQueue
        from models.order import Order
        
        # Obtener reintentos pendientes que no estén completados y tengan menos intentos que max_retries
        pending_retries = SaleRetryQueue.query.filter(
            and_(
                SaleRetryQueue.status != 'completed',
                SaleRetryQueue.status != 'done',  # Por si acaso hay registros antiguos con 'done'
                SaleRetryQueue.retry_count < SaleRetryQueue.max_retries
            )
        ).all()
        
        if not pending_retries:
            return success_response(
                data={
                    "processed_count": 0,
                    "successful_count": 0,
                    "failed_count": 0,
                    "skipped_count": 0
                },
                message="No hay reintentos pendientes para procesar"
            )
        
        processed_count = 0
        successful_count = 0
        failed_count = 0
        skipped_count = 0
        
        now = datetime.utcnow()
        
        # Importar crear_venta y Flask current_app
        from flask import current_app
        from routes.public_api import crear_venta
        
        # Procesar cada reintento secuencialmente (más seguro para DB)
        for retry in pending_retries:
            retry_id = str(retry.id)
            try:
                # Verificar nuevamente que no esté completado o haya alcanzado max_retries
                if retry.status in ['done', 'completed'] or retry.retry_count >= retry.max_retries:
                    skipped_count += 1
                    continue
                
                processed_count += 1
                
                # Refrescar el objeto para asegurar que tenemos los datos más recientes
                db.session.refresh(retry)
                
                # Actualizar status a 'processing'
                retry.status = 'processing'
                retry.last_retry_at = now
                retry.retry_count += 1
                db.session.flush()  # Flush antes del commit
                db.session.commit()
                
                # Refrescar después del commit para asegurar que los cambios se persistan
                db.session.refresh(retry)
                print(f"[DEBUG process_sale_retries] Retry {retry.id} actualizado - status={retry.status}, retry_count={retry.retry_count}")
                
                # Obtener el crm_payload
                crm_payload = retry.crm_payload
                if not crm_payload:
                    error_msg = "No se encontró crm_payload"
                    retry.status = 'failed'
                    retry.error_message = error_msg
                    retry.completed_at = now
                    db.session.flush()
                    db.session.commit()
                    db.session.refresh(retry)
                    failed_count += 1
                    print(f"[DEBUG process_sale_retries] ⚠️ Retry {retry.id} falló: {error_msg}")
                    continue
                
                print(f"[DEBUG process_sale_retries] Procesando retry {retry.id}, intento {retry.retry_count}")
                
                # Llamar a crear_venta usando test_request_context
                try:
                    with current_app.test_request_context(
                        '/api/ventas/crear',
                        method='POST',
                        json=crm_payload,
                        headers={'Authorization': f'Bearer {Config.API_KEY}'}
                    ):
                        response = crear_venta()
                        
                        if isinstance(response, tuple):
                            response_obj, status_code = response
                        else:
                            response_obj = response
                            status_code = response_obj.status_code if hasattr(response_obj, 'status_code') else 200
                        
                        # Obtener response_data
                        response_data = {}
                        try:
                            if hasattr(response_obj, 'get_json'):
                                response_data = response_obj.get_json() or {}
                            elif hasattr(response_obj, 'data'):
                                response_data = json.loads(response_obj.data.decode('utf-8'))
                            elif isinstance(response_obj, dict):
                                response_data = response_obj
                        except Exception as parse_error:
                            print(f"[DEBUG process_sale_retries] ⚠️ Error al parsear respuesta: {str(parse_error)}")
                            response_data = {'error': f'Error al parsear respuesta: {str(parse_error)}'}
                        
                        # Refrescar el retry antes de actualizar (puede haber cambiado)
                        db.session.refresh(retry)
                        
                        # Verificar si fue exitoso
                        if status_code == 200 and response_data.get('status', False):
                            external_venta_id = response_data.get('data', {}).get('crm_order_id') or response_data.get('data', {}).get('venta_id')
                            
                            if external_venta_id:
                                # Éxito: actualizar el retry como completado
                                retry.status = 'completed'  # Usar 'completed' en lugar de 'done'
                                retry.completed_at = now
                                retry.error_message = None
                                retry.error_details = {
                                    "success": True,
                                    "status_code": status_code,
                                    "crm_order_id": external_venta_id
                                }
                                
                                # Si hay order_id, actualizar la orden con el crm_order_id
                                if retry.order_id:
                                    order = db.session.query(Order).filter_by(id=retry.order_id).first()
                                    if order:
                                        order.crm_order_id = external_venta_id
                                        print(f"[DEBUG process_sale_retries] ✅ Orden {order.id} actualizada con crm_order_id={external_venta_id}")
                                
                                try:
                                    db.session.flush()
                                    db.session.commit()
                                    db.session.refresh(retry)
                                    successful_count += 1
                                    print(f"[DEBUG process_sale_retries] ✅ Retry {retry.id} completado exitosamente con crm_order_id={external_venta_id}, status={retry.status}, retry_count={retry.retry_count}")
                                except Exception as commit_error:
                                    db.session.rollback()
                                    print(f"[DEBUG process_sale_retries] ⚠️ Error al hacer commit del retry {retry.id}: {str(commit_error)}")
                                    # Intentar de nuevo con un nuevo query
                                    retry = db.session.query(SaleRetryQueue).filter_by(id=retry.id).first()
                                    if retry:
                                        retry.status = 'completed'
                                        retry.completed_at = now
                                        retry.error_message = None
                                        retry.error_details = {
                                            "success": True,
                                            "status_code": status_code,
                                            "crm_order_id": external_venta_id
                                        }
                                        db.session.commit()
                                        successful_count += 1
                                    else:
                                        failed_count += 1
                            else:
                                # No se pudo obtener el venta_id
                                error_msg = f"No se pudo obtener el ID de venta. Response: {json.dumps(response_data, default=str)}"
                                retry.status = 'pending' if retry.retry_count < retry.max_retries else 'failed'
                                retry.error_message = error_msg
                                retry.error_details = {
                                    "success": False,
                                    "status_code": status_code,
                                    "response": response_data
                                }
                                if retry.retry_count >= retry.max_retries:
                                    retry.completed_at = now
                                try:
                                    db.session.flush()
                                    db.session.commit()
                                    db.session.refresh(retry)
                                    failed_count += 1
                                    print(f"[DEBUG process_sale_retries] ⚠️ Retry {retry.id} falló: {error_msg}, status={retry.status}, retry_count={retry.retry_count}")
                                except Exception as commit_error:
                                    db.session.rollback()
                                    print(f"[DEBUG process_sale_retries] ⚠️ Error al hacer commit del retry {retry.id}: {str(commit_error)}")
                                    failed_count += 1
                        else:
                            # Error en la respuesta
                            error_msg = response_data.get('message', f'Error al crear venta: status_code={status_code}, response={json.dumps(response_data, default=str)}')
                            retry.status = 'pending' if retry.retry_count < retry.max_retries else 'failed'
                            retry.error_message = error_msg
                            retry.error_details = {
                                "success": False,
                                "status_code": status_code,
                                "response": response_data
                            }
                            if retry.retry_count >= retry.max_retries:
                                retry.completed_at = now
                            try:
                                db.session.flush()
                                db.session.commit()
                                db.session.refresh(retry)
                                failed_count += 1
                                print(f"[DEBUG process_sale_retries] ⚠️ Retry {retry.id} falló: {error_msg}, status={retry.status}, retry_count={retry.retry_count}")
                            except Exception as commit_error:
                                db.session.rollback()
                                print(f"[DEBUG process_sale_retries] ⚠️ Error al hacer commit del retry {retry.id}: {str(commit_error)}")
                                failed_count += 1
                            
                except Exception as ext_error:
                    # Cualquier otro error
                    import traceback
                    from sqlalchemy.exc import IntegrityError, PendingRollbackError
                    error_traceback = traceback.format_exc()
                    error_msg = f"Error inesperado: {str(ext_error)}"
                    
                    # Hacer rollback si hay un error pendiente
                    try:
                        db.session.rollback()
                    except:
                        pass
                    
                    # Obtener el retry de nuevo después del rollback
                    try:
                        retry = db.session.query(SaleRetryQueue).filter_by(id=retry_id).first()
                    except:
                        retry = None
                    
                    if retry:
                        try:
                            retry.status = 'pending' if retry.retry_count < retry.max_retries else 'failed'
                            retry.error_message = error_msg
                            retry.error_details = {
                                "success": False,
                                "error": str(ext_error),
                                "error_type": type(ext_error).__name__,
                                "traceback": error_traceback
                            }
                            if retry.retry_count >= retry.max_retries:
                                retry.completed_at = now
                            db.session.flush()
                            db.session.commit()
                            db.session.refresh(retry)
                        except Exception as update_error:
                            db.session.rollback()
                            print(f"[DEBUG process_sale_retries] ⚠️ Error al actualizar retry {retry_id} después de error: {str(update_error)}")
                    
                    failed_count += 1
                    print(f"[DEBUG process_sale_retries] ⚠️ Retry {retry_id} falló: {error_msg}")
                    print(f"Traceback:\n{error_traceback}")
                    
            except Exception as retry_error:
                # Error al procesar un retry individual
                import traceback
                error_traceback = traceback.format_exc()
                error_msg = f"Error al procesar: {str(retry_error)}"
                print(f"[DEBUG process_sale_retries] ⚠️ Error al procesar retry {retry_id}: {error_msg}")
                print(f"Traceback:\n{error_traceback}")
                
                # Intentar actualizar el status incluso si hay error
                try:
                    retry = db.session.query(SaleRetryQueue).filter_by(id=retry_id).first()
                    if retry:
                        retry.status = 'pending' if retry.retry_count < retry.max_retries else 'failed'
                        retry.error_message = error_msg
                        if retry.retry_count >= retry.max_retries:
                            retry.completed_at = datetime.utcnow()
                        db.session.flush()
                        db.session.commit()
                        db.session.refresh(retry)
                        print(f"[DEBUG process_sale_retries] Retry {retry_id} actualizado después de error - status={retry.status}, retry_count={retry.retry_count}")
                except Exception as update_error:
                    print(f"[DEBUG process_sale_retries] ⚠️ Error al actualizar status del retry {retry_id}: {str(update_error)}")
                    try:
                        db.session.rollback()
                    except:
                        pass
                
                failed_count += 1
        
        return success_response(
            data={
                "processed_count": processed_count,
                "successful_count": successful_count,
                "failed_count": failed_count,
                "skipped_count": skipped_count
            },
            message=f"Se procesaron {processed_count} reintentos: {successful_count} exitosos, {failed_count} fallidos, {skipped_count} omitidos"
        )
        
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"Error en process_sale_retries: {str(e)}")
        print(f"Traceback completo:\n{error_traceback}")
        return server_error(f"Error al procesar los reintentos: {str(e)}")
