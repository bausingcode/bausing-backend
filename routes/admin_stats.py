from flask import Blueprint, request, jsonify
from database import db
from sqlalchemy import text
from datetime import datetime, timedelta
from routes.admin_auth import admin_required

admin_stats_bp = Blueprint('admin_stats', __name__)

@admin_stats_bp.route('/dashboard/stats', methods=['GET'])
@admin_required
def get_dashboard_stats():
    """
    Obtiene estadísticas del dashboard calculadas directamente en SQL (muy rápido)
    """
    try:
        hoy = datetime.utcnow().date()
        ayer = hoy - timedelta(days=1)
        
        # Lunes de esta semana
        inicio_semana = hoy - timedelta(days=hoy.weekday())
        inicio_semana_anterior = inicio_semana - timedelta(days=7)
        
        # Inicio del mes
        inicio_mes = hoy.replace(day=1)
        inicio_mes_anterior = (inicio_mes - timedelta(days=1)).replace(day=1)
        fin_mes_anterior = inicio_mes - timedelta(days=1)
        
        # Query optimizado que calcula todo en SQL
        query = text("""
            WITH ventas_por_fecha AS (
                SELECT 
                    detail_date::date as fecha,
                    total_sale,
                    status,
                    CASE WHEN is_cancelled THEN 1 ELSE 0 END as cancelada
                FROM crm_orders
                WHERE detail_date IS NOT NULL
            )
            SELECT 
                -- Ventas de hoy
                COALESCE(SUM(CASE WHEN fecha = :hoy THEN total_sale ELSE 0 END), 0) as total_hoy,
                COALESCE(SUM(CASE WHEN fecha = :ayer THEN total_sale ELSE 0 END), 0) as total_ayer,
                -- Ventas semanales
                COALESCE(SUM(CASE WHEN fecha >= :inicio_semana AND fecha <= :hoy THEN total_sale ELSE 0 END), 0) as total_semana,
                COALESCE(SUM(CASE WHEN fecha >= :inicio_semana_anterior AND fecha < :inicio_semana THEN total_sale ELSE 0 END), 0) as total_semana_anterior,
                -- Ventas mensuales
                COALESCE(SUM(CASE WHEN fecha >= :inicio_mes AND fecha <= :hoy THEN total_sale ELSE 0 END), 0) as total_mes,
                COALESCE(SUM(CASE WHEN fecha >= :inicio_mes_anterior AND fecha <= :fin_mes_anterior THEN total_sale ELSE 0 END), 0) as total_mes_anterior,
                -- Contadores por estado
                COUNT(CASE WHEN LOWER(status) LIKE '%pagado%' OR LOWER(status) LIKE '%pago%' THEN 1 END) as pagados,
                COUNT(CASE WHEN LOWER(status) LIKE '%pendiente%' THEN 1 END) as pendientes,
                COUNT(CASE WHEN LOWER(status) LIKE '%reparto%' OR LOWER(status) LIKE '%enviado%' OR LOWER(status) LIKE '%transito%' THEN 1 END) as en_reparto,
                COUNT(CASE WHEN LOWER(status) LIKE '%entregado%' OR LOWER(status) LIKE '%finalizado%' THEN 1 END) as entregados,
                -- Total de pedidos
                COUNT(*) as total_pedidos,
                COUNT(CASE WHEN fecha >= :inicio_mes AND fecha <= :hoy THEN 1 END) as pedidos_mes,
                COUNT(CASE WHEN fecha >= :inicio_mes_anterior AND fecha <= :fin_mes_anterior THEN 1 END) as pedidos_mes_anterior
            FROM ventas_por_fecha
            WHERE cancelada = 0
        """)
        
        result = db.session.execute(query, {
            'hoy': hoy,
            'ayer': ayer,
            'inicio_semana': inicio_semana,
            'inicio_semana_anterior': inicio_semana_anterior,
            'inicio_mes': inicio_mes,
            'inicio_mes_anterior': inicio_mes_anterior,
            'fin_mes_anterior': fin_mes_anterior
        })
        
        row = result.fetchone()
        
        if not row:
            stats = {
                'ventas_hoy': 0.0,
                'ventas_ayer': 0.0,
                'ventas_semana': 0.0,
                'ventas_semana_anterior': 0.0,
                'ventas_mes': 0.0,
                'ventas_mes_anterior': 0.0,
                'total_pedidos': 0,
                'pedidos_mes': 0,
                'pedidos_mes_anterior': 0,
                'estados': {
                    'pagados': 0,
                    'pendientes': 0,
                    'en_reparto': 0,
                    'entregados': 0
                }
            }
        else:
            cambio_hoy = ((row.total_hoy - row.total_ayer) / row.total_ayer * 100) if row.total_ayer > 0 else (100 if row.total_hoy > 0 else 0)
            cambio_semana = ((row.total_semana - row.total_semana_anterior) / row.total_semana_anterior * 100) if row.total_semana_anterior > 0 else (100 if row.total_semana > 0 else 0)
            cambio_mes = ((row.total_mes - row.total_mes_anterior) / row.total_mes_anterior * 100) if row.total_mes_anterior > 0 else (100 if row.total_mes > 0 else 0)
            
            stats = {
                'ventas_hoy': float(row.total_hoy or 0),
                'ventas_ayer': float(row.total_ayer or 0),
                'cambio_hoy_pct': cambio_hoy,
                'ventas_semana': float(row.total_semana or 0),
                'ventas_semana_anterior': float(row.total_semana_anterior or 0),
                'cambio_semana_pct': cambio_semana,
                'ventas_mes': float(row.total_mes or 0),
                'ventas_mes_anterior': float(row.total_mes_anterior or 0),
                'cambio_mes_pct': cambio_mes,
                'total_pedidos': int(row.total_pedidos or 0),
                'pedidos_mes': int(row.pedidos_mes or 0),
                'pedidos_mes_anterior': int(row.pedidos_mes_anterior or 0),
                'cambio_pedidos': int(row.pedidos_mes or 0) - int(row.pedidos_mes_anterior or 0),
                'estados': {
                    'pagados': int(row.pagados or 0),
                    'pendientes': int(row.pendientes or 0),
                    'en_reparto': int(row.en_reparto or 0),
                    'entregados': int(row.entregados or 0)
                }
            }
        
        return jsonify({
            'success': True,
            'data': stats
        }), 200
        
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error en get_dashboard_stats: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_stats_bp.route('/logistica/pedidos', methods=['GET'])
@admin_required
def get_logistica_pedidos():
    """
    Obtiene pedidos para logística optimizado - solo campos necesarios, sin renglones ni pagos
    """
    try:
        search = request.args.get('search')
        solo_retrasos = request.args.get('solo_retrasos', 'false').lower() == 'true'
        dias_estimados = int(request.args.get('dias_estimados', 3))
        
        # Query optimizado - solo campos necesarios para logística
        query_base = """
            SELECT 
                co.crm_order_id as id,
                co.receipt_number as numero_comprobante,
                co.crm_created_at as fecha_detalle,
                co.client_name as cliente_nombre,
                co.client_address as cliente_direccion,
                co.city as localidad,
                co.crm_zone_id as zona_id,
                co.status as estado,
                co.total_sale as total_venta,
                CASE WHEN co.is_cancelled THEN 1 ELSE 0 END as venta_cancelada,
                co.delivery_date as fecha_entrega
            FROM crm_orders co
            WHERE co.is_cancelled = false
                AND LOWER(co.status) NOT LIKE '%entregado%'
                AND LOWER(co.status) NOT LIKE '%finalizado%'
                AND LOWER(co.status) NOT LIKE '%cancelado%'
        """
        
        conditions = []
        params = {}
        
        # Filtro de búsqueda
        if search:
            conditions.append("""
                (co.receipt_number ILIKE :search OR 
                 co.client_name ILIKE :search OR 
                 co.crm_order_id::text ILIKE :search)
            """)
            params['search'] = f'%{search}%'
        
        # Filtro de retrasos (si está activo) - calcular en SQL
        if solo_retrasos:
            fecha_limite = datetime.utcnow().date() - timedelta(days=dias_estimados)
            conditions.append("""
                (co.delivery_date IS NULL AND co.crm_created_at::date < :fecha_limite OR
                 co.delivery_date IS NOT NULL AND co.delivery_date::date < CURRENT_DATE)
            """)
            params['fecha_limite'] = fecha_limite
        
        where_clause = " AND " + " AND ".join(conditions) if conditions else ""
        
        query = text(query_base + where_clause + " ORDER BY co.crm_order_id DESC LIMIT 200")
        
        result = db.session.execute(query, params)
        rows = result.fetchall()
        
        ventas = []
        for row in rows:
            ventas.append({
                'id': row.id,
                'numero_comprobante': row.numero_comprobante,
                'fecha_detalle': row.fecha_detalle.strftime('%Y-%m-%d') if row.fecha_detalle else None,
                'fecha_entrega': row.fecha_entrega.strftime('%Y-%m-%d %H:%M:%S') if row.fecha_entrega else None,
                'cliente_nombre': row.cliente_nombre,
                'cliente_direccion': row.cliente_direccion,
                'localidad': row.localidad,
                'zona_id': row.zona_id,
                'estado': row.estado,
                'total_venta': float(row.total_venta) if row.total_venta else 0.0,
                'venta_cancelada': row.venta_cancelada
            })
        
        return jsonify({
            'success': True,
            'data': {
                'ventas': ventas,
                'total': len(ventas)
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error en get_logistica_pedidos: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500



@admin_stats_bp.route('/dashboard/alerts', methods=['GET'])
@admin_required
def get_dashboard_alerts():
    """
    Obtiene alertas del dashboard (retrasos en entregas, reclamos, anomalías en billetera)
    """
    try:
        hoy = datetime.utcnow().date()
        
        # Obtener días estimados de configuración (por defecto 3)
        from models.settings import SystemSettings
        dias_estimados = SystemSettings.get_value('general.estimated_shipping_days', default=3)
        if isinstance(dias_estimados, (int, float)):
            dias_estimados = int(dias_estimados)
        else:
            dias_estimados = 3
        
        fecha_limite = hoy - timedelta(days=dias_estimados)
        
        # Debug: imprimir valores para troubleshooting
        print(f"DEBUG alerts - hoy: {hoy}, dias_estimados: {dias_estimados}, fecha_limite: {fecha_limite}")
        
        # 1. Retrasos en entregas (de logística)
        # Lógica exactamente igual al frontend:
        # - Si tiene delivery_date (real): hoy > delivery_date (estricto) Y estado != entregado
        # - Si NO tiene delivery_date: hoy > (crm_created_at + dias_estimados) 
        # En SQL:
        #   - Para retraso real: delivery_date::date < CURRENT_DATE (excluyendo hoy)
        #   - Para retraso estimado: crm_created_at::date + dias_estimados < CURRENT_DATE
        #     Esto es equivalente a: crm_created_at::date < (CURRENT_DATE - dias_estimados) = fecha_limite
        query_retrasos = text("""
            SELECT COUNT(*) as total
            FROM crm_orders co
            WHERE co.is_cancelled = false
                AND LOWER(co.status) NOT LIKE '%entregado%'
                AND LOWER(co.status) NOT LIKE '%finalizado%'
                AND LOWER(co.status) NOT LIKE '%cancelado%'
                AND (
                    -- Retraso real: tiene delivery_date y ya pasó (hoy > delivery_date, estricto)
                    (co.delivery_date IS NOT NULL AND co.delivery_date::date < CURRENT_DATE)
                    OR
                    -- Retraso estimado: no tiene delivery_date pero la fecha estimada ya pasó
                    -- Si crm_created_at + dias_estimados < CURRENT_DATE, entonces hoy > (crm_created_at + dias_estimados)
                    -- Usamos fecha_limite = hoy - dias_estimados, entonces crm_created_at::date < fecha_limite
                    (co.delivery_date IS NULL 
                     AND co.crm_created_at IS NOT NULL 
                     AND co.crm_created_at::date < :fecha_limite)
                )
        """)
        
        result_retrasos = db.session.execute(query_retrasos, {'fecha_limite': fecha_limite})
        retrasos_count = result_retrasos.scalar() or 0
        
        print(f"DEBUG alerts - retrasos_count: {retrasos_count}")
        
        # Debug adicional: contar pedidos por tipo de retraso
        if retrasos_count > 0:
            query_debug = text("""
                SELECT 
                    COUNT(CASE WHEN co.delivery_date IS NOT NULL THEN 1 END) as retrasos_reales,
                    COUNT(CASE WHEN co.delivery_date IS NULL THEN 1 END) as retrasos_estimados
                FROM crm_orders co
                WHERE co.is_cancelled = false
                    AND LOWER(co.status) NOT LIKE '%entregado%'
                    AND LOWER(co.status) NOT LIKE '%finalizado%'
                    AND LOWER(co.status) NOT LIKE '%cancelado%'
                    AND (
                        (co.delivery_date IS NOT NULL AND co.delivery_date::date < CURRENT_DATE)
                        OR
                        (co.delivery_date IS NULL 
                         AND co.crm_created_at IS NOT NULL 
                         AND co.crm_created_at::date < :fecha_limite)
                    )
            """)
            result_debug = db.session.execute(query_debug, {'fecha_limite': fecha_limite})
            row_debug = result_debug.fetchone()
            if row_debug:
                print(f"DEBUG alerts - retrasos_reales: {row_debug[0]}, retrasos_estimados: {row_debug[1]}")
        
        # 2. Movimientos inusuales en billetera
        from models.wallet import WalletMovement, Wallet
        from models.user import User
        from sqlalchemy import func
        
        manual_types = ['manual_credit', 'manual_debit']
        usuarios_inusuales = db.session.query(
            func.count(func.distinct(User.id)).label('count')
        ).outerjoin(Wallet, User.id == Wallet.user_id)\
         .outerjoin(WalletMovement, Wallet.id == WalletMovement.wallet_id)\
         .filter(WalletMovement.type.in_(manual_types))\
         .group_by(User.id)\
         .having(func.count(WalletMovement.id) >= 5)\
         .all()
        
        movimientos_inusuales_count = len(usuarios_inusuales) if usuarios_inusuales else 0
        
        # 3. Reclamos abiertos pendientes (por ahora 0)
        reclamos_abiertos_count = 0
        
        alerts = []
        
        if retrasos_count > 0:
            alerts.append({
                'text': 'Retrasos en entregas',
                'count': retrasos_count,
                'color': 'red',
                'url': '/admin/logistica'
            })
        
        if reclamos_abiertos_count > 0:
            alerts.append({
                'text': 'Reclamos abiertos pendientes',
                'count': reclamos_abiertos_count,
                'color': 'yellow',
                'url': None  # No hay página de reclamos aún
            })
        
        if movimientos_inusuales_count > 0:
            alerts.append({
                'text': 'Movimientos inusuales en billetera',
                'count': movimientos_inusuales_count,
                'color': 'blue',
                'url': '/admin/billetera'
            })
        
        return jsonify({
            'success': True,
            'data': {
                'alerts': alerts,
                'total': len(alerts)
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error en get_dashboard_alerts: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_stats_bp.route('/dashboard/wallet-usage', methods=['GET'])
@admin_required
def get_wallet_usage():
    """
    Obtiene estadísticas de uso de billetera Bausing
    """
    try:
        hoy = datetime.utcnow().date()
        inicio_hoy = datetime.combine(hoy, datetime.min.time())
        fin_hoy = datetime.combine(hoy, datetime.max.time())
        
        # 1. Clientes que usaron hoy
        query_clientes_hoy = text("""
            SELECT COUNT(DISTINCT w.user_id) as total
            FROM wallet_movements wm
            INNER JOIN wallets w ON wm.wallet_id = w.id
            WHERE wm.type IN ('purchase', 'transfer_out', 'expiration', 'debit', 'manual_debit')
                AND wm.created_at >= :inicio_hoy
                AND wm.created_at <= :fin_hoy
        """)
        
        result_clientes = db.session.execute(query_clientes_hoy, {
            'inicio_hoy': inicio_hoy,
            'fin_hoy': fin_hoy
        })
        clientes_hoy = result_clientes.scalar() or 0
        
        # 2. Saldo total utilizado hoy
        query_saldo_utilizado = text("""
            SELECT COALESCE(ABS(SUM(wm.amount)), 0) as total
            FROM wallet_movements wm
            WHERE wm.type IN ('purchase', 'transfer_out', 'expiration', 'debit', 'manual_debit')
                AND wm.created_at >= :inicio_hoy
                AND wm.created_at <= :fin_hoy
        """)
        
        result_saldo_utilizado = db.session.execute(query_saldo_utilizado, {
            'inicio_hoy': inicio_hoy,
            'fin_hoy': fin_hoy
        })
        saldo_utilizado = float(result_saldo_utilizado.scalar() or 0)
        
        # 3. Saldo pendiente en sistema
        query_saldo_pendiente = text("""
            SELECT COALESCE(SUM(balance), 0) as total
            FROM wallets
            WHERE balance > 0
        """)
        
        result_saldo_pendiente = db.session.execute(query_saldo_pendiente)
        saldo_pendiente = float(result_saldo_pendiente.scalar() or 0)
        
        return jsonify({
            'success': True,
            'data': {
                'clientes_hoy': int(clientes_hoy),
                'saldo_utilizado': saldo_utilizado,
                'saldo_pendiente': saldo_pendiente
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error en get_wallet_usage: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_stats_bp.route('/users/<uuid:user_id>/metrics', methods=['GET'])
@admin_required
def get_user_metrics(user_id):
    """
    Obtiene métricas detalladas de un usuario específico
    """
    try:
        from models.user import User
        from models.order import Order
        from models.wallet import Wallet
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'error': 'Usuario no encontrado'
            }), 404
        
        # Calcular métricas de órdenes
        # Consideramos órdenes completadas aquellas con status que contenga "entregado", "finalizado", "completado" o "pagado"
        query_orders = text("""
            SELECT 
                COUNT(*) as total_orders,
                COUNT(CASE WHEN LOWER(status) LIKE '%entregado%' 
                          OR LOWER(status) LIKE '%finalizado%' 
                          OR LOWER(status) LIKE '%completado%' 
                          OR LOWER(status) LIKE '%pagado%' THEN 1 END) as completed_orders,
                COUNT(CASE WHEN LOWER(status) LIKE '%pendiente%' THEN 1 END) as pending_orders,
                COUNT(CASE WHEN LOWER(status) LIKE '%cancelado%' THEN 1 END) as cancelled_orders,
                COALESCE(SUM(CASE WHEN LOWER(status) LIKE '%entregado%' 
                                  OR LOWER(status) LIKE '%finalizado%' 
                                  OR LOWER(status) LIKE '%completado%' 
                                  OR LOWER(status) LIKE '%pagado%' THEN total ELSE 0 END), 0) as total_spent,
                COALESCE(AVG(CASE WHEN LOWER(status) LIKE '%entregado%' 
                                  OR LOWER(status) LIKE '%finalizado%' 
                                  OR LOWER(status) LIKE '%completado%' 
                                  OR LOWER(status) LIKE '%pagado%' THEN total END), 0) as avg_order_value,
                MAX(CASE WHEN LOWER(status) LIKE '%entregado%' 
                            OR LOWER(status) LIKE '%finalizado%' 
                            OR LOWER(status) LIKE '%completado%' 
                            OR LOWER(status) LIKE '%pagado%' THEN created_at END) as last_purchase_date,
                MIN(CASE WHEN LOWER(status) LIKE '%entregado%' 
                            OR LOWER(status) LIKE '%finalizado%' 
                            OR LOWER(status) LIKE '%completado%' 
                            OR LOWER(status) LIKE '%pagado%' THEN created_at END) as first_purchase_date
            FROM orders
            WHERE user_id = :user_id
        """)
        
        result_orders = db.session.execute(query_orders, {'user_id': user_id})
        row_orders = result_orders.fetchone()
        
        # Calcular días desde última compra
        days_since_last_purchase = None
        if row_orders and row_orders.last_purchase_date:
            days_since_last_purchase = (datetime.utcnow().date() - row_orders.last_purchase_date.date()).days
        
        # Obtener información de billetera
        wallet = Wallet.query.filter_by(user_id=user_id).first()
        wallet_balance = float(wallet.balance) if wallet else 0.0
        
        # Calcular "carritos abandonados" - esto es una aproximación
        # Un carrito abandonado sería una orden pendiente que no se completó en X días
        # Por ahora, consideramos órdenes pendientes como potenciales carritos abandonados
        abandoned_carts_count = row_orders.pending_orders if row_orders else 0
        
        # Calcular valor de órdenes pendientes (potenciales carritos abandonados)
        query_abandoned_value = text("""
            SELECT COALESCE(SUM(total), 0) as total_value
            FROM orders
            WHERE user_id = :user_id
                AND LOWER(status) LIKE '%pendiente%'
        """)
        
        result_abandoned = db.session.execute(query_abandoned_value, {'user_id': user_id})
        abandoned_carts_value = float(result_abandoned.scalar() or 0)
        
        metrics = {
            'user_id': str(user_id),
            'user_name': f"{user.first_name} {user.last_name}",
            'user_email': user.email,
            'orders': {
                'total': int(row_orders.total_orders or 0) if row_orders else 0,
                'completed': int(row_orders.completed_orders or 0) if row_orders else 0,
                'pending': int(row_orders.pending_orders or 0) if row_orders else 0,
                'cancelled': int(row_orders.cancelled_orders or 0) if row_orders else 0
            },
            'purchases': {
                'total_spent': float(row_orders.total_spent or 0) if row_orders else 0.0,
                'avg_order_value': float(row_orders.avg_order_value or 0) if row_orders else 0.0,
                'last_purchase_date': row_orders.last_purchase_date.isoformat() if row_orders and row_orders.last_purchase_date else None,
                'first_purchase_date': row_orders.first_purchase_date.isoformat() if row_orders and row_orders.first_purchase_date else None,
                'days_since_last_purchase': days_since_last_purchase
            },
            'abandoned_carts': {
                'count': abandoned_carts_count,
                'total_value': abandoned_carts_value
            },
            'wallet': {
                'balance': wallet_balance
            },
            'conversion_rate': (
                (int(row_orders.completed_orders or 0) / int(row_orders.total_orders or 1) * 100) 
                if row_orders and row_orders.total_orders > 0 else 0.0
            )
        }
        
        return jsonify({
            'success': True,
            'data': metrics
        }), 200
        
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error en get_user_metrics: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_stats_bp.route('/users/metrics', methods=['GET'])
@admin_required
def get_users_metrics():
    """
    Obtiene métricas agregadas de todos los usuarios con paginación
    """
    try:
        from models.user import User
        
        # Parámetros de paginación
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        search = request.args.get('search', '').strip()
        
        # Validar parámetros
        page = max(1, page)
        per_page = min(max(1, per_page), 100)  # Máximo 100 por página
        
        # Query base para métricas de usuarios
        query_base = text("""
            SELECT 
                u.id,
                u.first_name,
                u.last_name,
                u.email,
                u.created_at as user_created_at,
                COUNT(DISTINCT o.id) as total_orders,
                COUNT(DISTINCT CASE WHEN LOWER(o.status) LIKE '%entregado%' 
                                      OR LOWER(o.status) LIKE '%finalizado%' 
                                      OR LOWER(o.status) LIKE '%completado%' 
                                      OR LOWER(o.status) LIKE '%pagado%' THEN o.id END) as completed_orders,
                COUNT(DISTINCT CASE WHEN LOWER(o.status) LIKE '%pendiente%' THEN o.id END) as pending_orders,
                COALESCE(SUM(CASE WHEN LOWER(o.status) LIKE '%entregado%' 
                                    OR LOWER(o.status) LIKE '%finalizado%' 
                                    OR LOWER(o.status) LIKE '%completado%' 
                                    OR LOWER(o.status) LIKE '%pagado%' THEN o.total ELSE 0 END), 0) as total_spent,
                COALESCE(AVG(CASE WHEN LOWER(o.status) LIKE '%entregado%' 
                                    OR LOWER(o.status) LIKE '%finalizado%' 
                                    OR LOWER(o.status) LIKE '%completado%' 
                                    OR LOWER(o.status) LIKE '%pagado%' THEN o.total END), 0) as avg_order_value,
                MAX(CASE WHEN LOWER(o.status) LIKE '%entregado%' 
                            OR LOWER(o.status) LIKE '%finalizado%' 
                            OR LOWER(o.status) LIKE '%completado%' 
                            OR LOWER(o.status) LIKE '%pagado%' THEN o.created_at END) as last_purchase_date,
                COALESCE(w.balance, 0) as wallet_balance
            FROM users u
            LEFT JOIN orders o ON u.id = o.user_id
            LEFT JOIN wallets w ON u.id = w.user_id
            WHERE 1=1
        """)
        
        params = {}
        conditions = []
        
        # Filtro de búsqueda
        if search:
            conditions.append("""
                (u.first_name ILIKE :search OR 
                 u.last_name ILIKE :search OR 
                 u.email ILIKE :search)
            """)
            params['search'] = f'%{search}%'
        
        where_clause = " AND " + " AND ".join(conditions) if conditions else ""
        
        # Query completo con GROUP BY y paginación
        query = text(f"""
            {query_base}
            {where_clause}
            GROUP BY u.id, u.first_name, u.last_name, u.email, u.created_at, w.balance
            ORDER BY total_spent DESC, u.created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        
        params['limit'] = per_page
        params['offset'] = (page - 1) * per_page
        
        result = db.session.execute(query, params)
        rows = result.fetchall()
        
        # Contar total de usuarios (para paginación)
        count_query = text("""
            SELECT COUNT(DISTINCT u.id)
            FROM users u
            WHERE 1=1
        """ + where_clause)
        
        count_result = db.session.execute(count_query, {k: v for k, v in params.items() if k != 'limit' and k != 'offset'})
        total_users = count_result.scalar() or 0
        
        # Formatear resultados
        users_metrics = []
        for row in rows:
            days_since_last_purchase = None
            if row.last_purchase_date:
                days_since_last_purchase = (datetime.utcnow().date() - row.last_purchase_date.date()).days
            
            users_metrics.append({
                'user_id': str(row.id),
                'user_name': f"{row.first_name} {row.last_name}",
                'user_email': row.email,
                'user_created_at': row.user_created_at.isoformat() if row.user_created_at else None,
                'orders': {
                    'total': int(row.total_orders or 0),
                    'completed': int(row.completed_orders or 0),
                    'pending': int(row.pending_orders or 0)
                },
                'purchases': {
                    'total_spent': float(row.total_spent or 0),
                    'avg_order_value': float(row.avg_order_value or 0),
                    'last_purchase_date': row.last_purchase_date.isoformat() if row.last_purchase_date else None,
                    'days_since_last_purchase': days_since_last_purchase
                },
                'abandoned_carts': {
                    'count': int(row.pending_orders or 0),
                    'total_value': 0.0  # Se calcularía con una subquery si fuera necesario
                },
                'wallet': {
                    'balance': float(row.wallet_balance or 0)
                },
                'conversion_rate': (
                    (int(row.completed_orders or 0) / int(row.total_orders or 1) * 100) 
                    if row.total_orders > 0 else 0.0
                )
            })
        
        return jsonify({
            'success': True,
            'data': {
                'users': users_metrics,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total_users,
                    'total_pages': (total_users + per_page - 1) // per_page
                }
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error en get_users_metrics: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_stats_bp.route('/metrics/general', methods=['GET'])
@admin_required
def get_general_metrics():
    """
    Obtiene métricas generales/promedio de todos los usuarios
    Parámetros opcionales: start_date, end_date (formato YYYY-MM-DD)
    """
    try:
        from models.user import User
        
        # Obtener parámetros de fecha
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Construir filtro de fecha
        date_filter = ""
        params = {}
        if start_date or end_date:
            date_conditions = []
            if start_date:
                date_conditions.append("o.created_at >= :start_date")
                params['start_date'] = start_date
            if end_date:
                # Agregar un día completo al end_date para incluir todo el día
                from datetime import datetime, timedelta
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
                end_date_next = (end_date_obj + timedelta(days=1)).strftime('%Y-%m-%d')
                date_conditions.append("o.created_at < :end_date_next")
                params['end_date_next'] = end_date_next
            
            if date_conditions:
                date_filter = "AND " + " AND ".join(date_conditions)
        
        # Construir filtro de fecha para carritos
        cart_date_filter = ""
        cart_params = {}
        if start_date or end_date:
            cart_date_conditions = []
            if start_date:
                cart_date_conditions.append("c.created_at >= :cart_start_date")
                cart_params['cart_start_date'] = start_date
            if end_date:
                from datetime import datetime, timedelta
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
                end_date_next = (end_date_obj + timedelta(days=1)).strftime('%Y-%m-%d')
                cart_date_conditions.append("c.created_at < :cart_end_date_next")
                cart_params['cart_end_date_next'] = end_date_next
            
            if cart_date_conditions:
                cart_date_filter = "AND " + " AND ".join(cart_date_conditions)
        
        # Combinar parámetros
        all_params = {**(params if params else {}), **cart_params}
        
        # Query para métricas generales
        query = text(f"""
            WITH user_orders AS (
                SELECT 
                    u.id as user_id,
                    COUNT(DISTINCT o.id) as total_orders,
                    COUNT(DISTINCT CASE WHEN LOWER(o.status) LIKE '%entregado%' 
                                          OR LOWER(o.status) LIKE '%finalizado%' 
                                          OR LOWER(o.status) LIKE '%completado%' 
                                          OR LOWER(o.status) LIKE '%pagado%' THEN o.id END) as completed_orders,
                    COALESCE(SUM(CASE WHEN LOWER(o.status) LIKE '%entregado%' 
                                        OR LOWER(o.status) LIKE '%finalizado%' 
                                        OR LOWER(o.status) LIKE '%completado%' 
                                        OR LOWER(o.status) LIKE '%pagado%' THEN o.total ELSE 0 END), 0) as total_spent,
                    COALESCE(AVG(CASE WHEN LOWER(o.status) LIKE '%entregado%' 
                                        OR LOWER(o.status) LIKE '%finalizado%' 
                                        OR LOWER(o.status) LIKE '%completado%' 
                                        OR LOWER(o.status) LIKE '%pagado%' THEN o.total END), 0) as avg_order_value
                FROM users u
                LEFT JOIN orders o ON u.id = o.user_id {date_filter}
                GROUP BY u.id
            ),
            pending_orders_by_time AS (
                SELECT 
                    o.user_id,
                    COUNT(CASE WHEN o.created_at >= NOW() - INTERVAL '48 hours' THEN 1 END) as open_carts,
                    COUNT(CASE WHEN o.created_at < NOW() - INTERVAL '48 hours' THEN 1 END) as abandoned_carts
                FROM orders o
                WHERE LOWER(o.status) LIKE '%pendiente%'
                {date_filter if date_filter else ''}
                GROUP BY o.user_id
            )
            SELECT 
                COUNT(*) as total_users,
                COUNT(CASE WHEN uo.total_orders > 0 THEN 1 END) as users_with_orders,
                COUNT(CASE WHEN uo.completed_orders > 0 THEN 1 END) as users_with_purchases,
                COUNT(CASE WHEN pot.abandoned_carts > 0 THEN 1 END) as users_with_abandoned_carts,
                
                -- Promedios
                COALESCE(AVG(uo.total_orders), 0) as avg_orders_per_user,
                COALESCE(AVG(uo.completed_orders), 0) as avg_completed_orders_per_user,
                COALESCE(AVG(COALESCE(pot.open_carts, 0)), 0) as avg_open_carts_per_user,
                COALESCE(AVG(COALESCE(pot.abandoned_carts, 0)), 0) as avg_abandoned_carts_per_user,
                COALESCE(AVG(uo.total_spent), 0) as avg_spent_per_user,
                COALESCE(AVG(uo.avg_order_value), 0) as avg_order_value_general,
                
                -- Totales
                COALESCE(SUM(uo.total_orders), 0) as total_orders_all,
                COALESCE(SUM(uo.completed_orders), 0) as total_completed_orders,
                COALESCE(SUM(COALESCE(pot.open_carts, 0)), 0) as total_open_carts,
                COALESCE(SUM(COALESCE(pot.abandoned_carts, 0)), 0) as total_abandoned_carts,
                COALESCE(SUM(uo.total_spent), 0) as total_spent_all,
                0.0 as total_abandoned_value,
                
                -- Tasa de conversión promedio
                CASE 
                    WHEN SUM(uo.total_orders) > 0 
                    THEN (SUM(uo.completed_orders)::numeric / SUM(uo.total_orders)::numeric * 100)
                    ELSE 0 
                END as avg_conversion_rate
            FROM users u
            LEFT JOIN user_orders uo ON u.id = uo.user_id
            LEFT JOIN pending_orders_by_time pot ON u.id = pot.user_id
        """)
        
        result = db.session.execute(query, all_params if all_params else {})
        row = result.fetchone()
        
        if not row:
            metrics = {
                'total_users': 0,
                'users_with_orders': 0,
                'users_with_purchases': 0,
                'users_with_abandoned_carts': 0,
                'averages': {
                    'orders_per_user': 0.0,
                    'completed_orders_per_user': 0.0,
                    'open_carts_per_user': 0.0,
                    'pending_orders_per_user': 0.0,
                    'spent_per_user': 0.0,
                    'order_value': 0.0
                },
                'totals': {
                    'orders': 0,
                    'completed_orders': 0,
                    'open_carts': 0,
                    'pending_orders': 0,
                    'total_spent': 0.0,
                    'abandoned_carts_value': 0.0
                },
                'conversion_rate': 0.0
            }
        else:
            metrics = {
                'total_users': int(row.total_users or 0),
                'users_with_orders': int(row.users_with_orders or 0),
                'users_with_purchases': int(row.users_with_purchases or 0),
                'users_with_abandoned_carts': int(row.users_with_abandoned_carts or 0),
                'averages': {
                    'orders_per_user': float(row.avg_orders_per_user or 0),
                    'completed_orders_per_user': float(row.avg_completed_orders_per_user or 0),
                    'open_carts_per_user': float(row.avg_open_carts_per_user or 0),
                    'pending_orders_per_user': float(row.avg_abandoned_carts_per_user or 0),
                    'spent_per_user': float(row.avg_spent_per_user or 0),
                    'order_value': float(row.avg_order_value_general or 0)
                },
                'totals': {
                    'orders': int(row.total_orders_all or 0),
                    'completed_orders': int(row.total_completed_orders or 0),
                    'open_carts': int(row.total_open_carts or 0),
                    'pending_orders': int(row.total_abandoned_carts or 0),
                    'total_spent': float(row.total_spent_all or 0),
                    'abandoned_carts_value': float(row.total_abandoned_value or 0)
                },
                'conversion_rate': float(row.avg_conversion_rate or 0)
            }
        
        return jsonify({
            'success': True,
            'data': metrics
        }), 200
        
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error en get_general_metrics: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
