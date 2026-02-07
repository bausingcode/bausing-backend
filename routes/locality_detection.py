from flask import Blueprint, request, jsonify
from database import db
from models.crm_delivery_zone import CrmDeliveryZone, CrmZoneLocality
from models.locality import Locality
from config import Config
import requests
import json

locality_detection_bp = Blueprint('locality_detection', __name__)


def point_in_polygon(lon, lat, polygon_coordinates):
    """
    Verifica si un punto (lon, lat) está dentro de un polígono.
    Usa el algoritmo ray casting.
    
    Args:
        lon: Longitud del punto
        lat: Latitud del punto
        polygon_coordinates: Lista de coordenadas [[lon, lat], ...] del polígono
    
    Returns:
        True si el punto está dentro del polígono, False en caso contrario
    """
    if not polygon_coordinates or len(polygon_coordinates) < 3:
        return False
    
    # Asegurarse de que el polígono esté cerrado
    if polygon_coordinates[0] != polygon_coordinates[-1]:
        polygon_coordinates = polygon_coordinates + [polygon_coordinates[0]]
    
    n = len(polygon_coordinates)
    inside = False
    
    j = n - 1
    for i in range(n):
        xi, yi = polygon_coordinates[i]
        xj, yj = polygon_coordinates[j]
        
        # Verificar si el rayo cruza el borde
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        
        j = i
    
    return inside


def find_locality_by_coordinates(lon, lat):
    """
    Encuentra la localidad basada en coordenadas geográficas.
    Busca en todas las zonas de entrega y verifica si el punto está dentro de algún polígono.
    
    Args:
        lon: Longitud
        lat: Latitud
    
    Returns:
        Locality object o None si no se encuentra
    """
    print(f"[DEBUG] find_locality_by_coordinates: Buscando para lon={lon}, lat={lat}")
    
    # Obtener todas las zonas de entrega activas (no eliminadas)
    zones = CrmDeliveryZone.query.filter(
        CrmDeliveryZone.crm_deleted_at.is_(None)
    ).all()
    
    print(f"[DEBUG] Zonas de entrega encontradas: {len(zones)}")
    
    for idx, zone in enumerate(zones):
        print(f"[DEBUG] Procesando zona {idx + 1}/{len(zones)}: {zone.name} (crm_zone_id: {zone.crm_zone_id})")
        
        if not zone.surface_geojson:
            print(f"[DEBUG]   ⚠️  Zona {zone.name} no tiene surface_geojson, saltando")
            continue
        
        # El surface_geojson puede ser una lista de Features o un Feature único
        geojson_data = zone.surface_geojson
        print(f"[DEBUG]   Tipo de geojson_data: {type(geojson_data).__name__}")
        
        # Si es una lista, iterar sobre cada Feature
        if isinstance(geojson_data, list):
            print(f"[DEBUG]   Procesando lista de {len(geojson_data)} features")
            for feat_idx, feature in enumerate(geojson_data):
                if feature.get('type') == 'Feature' and feature.get('geometry'):
                    geometry = feature['geometry']
                    if geometry.get('type') == 'Polygon':
                        coordinates = geometry.get('coordinates', [])
                        if coordinates and len(coordinates) > 0:
                            # coordinates[0] es el anillo exterior del polígono
                            polygon_coords = coordinates[0]
                            print(f"[DEBUG]     Feature {feat_idx + 1}: Verificando punto en polígono con {len(polygon_coords)} vértices")
                            if point_in_polygon(lon, lat, polygon_coords):
                                print(f"[DEBUG]     ✅ Punto está dentro del polígono de la zona {zone.name}")
                                # Encontrar la localidad asociada a esta zona
                                zone_locality = CrmZoneLocality.query.filter_by(
                                    crm_zone_id=zone.crm_zone_id
                                ).first()
                                
                                if zone_locality and zone_locality.locality:
                                    print(f"[DEBUG]     ✅ Localidad encontrada: {zone_locality.locality.name}")
                                    return zone_locality.locality
                                else:
                                    print(f"[DEBUG]     ⚠️  Zona {zone.name} no tiene localidad asociada en crm_zone_localities")
                            else:
                                print(f"[DEBUG]     Punto NO está dentro del polígono")
        # Si es un Feature único
        elif isinstance(geojson_data, dict):
            print(f"[DEBUG]   Procesando Feature único")
            if geojson_data.get('type') == 'Feature' and geojson_data.get('geometry'):
                geometry = geojson_data['geometry']
                if geometry.get('type') == 'Polygon':
                    coordinates = geometry.get('coordinates', [])
                    if coordinates and len(coordinates) > 0:
                        polygon_coords = coordinates[0]
                        print(f"[DEBUG]     Verificando punto en polígono con {len(polygon_coords)} vértices")
                        if point_in_polygon(lon, lat, polygon_coords):
                            print(f"[DEBUG]     ✅ Punto está dentro del polígono de la zona {zone.name}")
                            zone_locality = CrmZoneLocality.query.filter_by(
                                crm_zone_id=zone.crm_zone_id
                            ).first()
                            
                            if zone_locality and zone_locality.locality:
                                print(f"[DEBUG]     ✅ Localidad encontrada: {zone_locality.locality.name}")
                                return zone_locality.locality
                            else:
                                print(f"[DEBUG]     ⚠️  Zona {zone.name} no tiene localidad asociada en crm_zone_localities")
                        else:
                            print(f"[DEBUG]     Punto NO está dentro del polígono")
            else:
                print(f"[DEBUG]   ⚠️  Feature no tiene geometry o tipo incorrecto")
        else:
            print(f"[DEBUG]   ⚠️  Tipo de geojson_data no reconocido: {type(geojson_data)}")
    
    print(f"[DEBUG] ❌ No se encontró ninguna localidad para las coordenadas proporcionadas")
    return None


def is_local_ip(ip_address):
    """
    Verifica si una IP es local (localhost, 127.0.0.1, etc.)
    
    Args:
        ip_address: Dirección IP
    
    Returns:
        True si es una IP local
    """
    if not ip_address:
        return True
    
    local_ips = ['127.0.0.1', 'localhost', '::1', '0.0.0.0']
    if ip_address in local_ips:
        return True
    
    # Verificar si es una IP privada (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
    parts = ip_address.split('.')
    if len(parts) == 4:
        try:
            first = int(parts[0])
            second = int(parts[1])
            if first == 192 and second == 168:
                return True
            if first == 10:
                return True
            if first == 172 and 16 <= second <= 31:
                return True
        except ValueError:
            pass
    
    return False


def get_coordinates_from_ip(ip_address, force_geolocation=False):
    """
    Obtiene las coordenadas geográficas desde una dirección IP.
    Usa el servicio ip-api.com (https://ip-api.com/docs/api:json)
    
    Plan gratuito: 45 requests por minuto por IP (sin API key requerida)
    No permite uso comercial en el plan gratuito
    
    Args:
        ip_address: Dirección IP
        force_geolocation: Si es True, intenta geolocalizar incluso si la IP parece local
    
    Returns:
        Tuple (lon, lat) o None si no se puede obtener
    """
    print(f"[DEBUG] get_coordinates_from_ip: Iniciando para IP: {ip_address}, force_geolocation: {force_geolocation}")
    
    if is_local_ip(ip_address) and not force_geolocation:
        print(f"⚠️  IP local detectada ({ip_address}). No se puede geolocalizar.")
        print(f"[DEBUG] Para desarrollo local, considera usar coordenadas directamente o configurar una IP pública")
        return None
    elif is_local_ip(ip_address) and force_geolocation:
        print(f"⚠️  IP local detectada ({ip_address}), pero force_geolocation=True. Intentando geolocalización de todas formas.")
    
    try:
        # Construir URL para ip-api.com
        # Formato: http://ip-api.com/json/{query}
        # No requiere API key para el plan gratuito
        url = f'http://ip-api.com/json/{ip_address}'
        headers = {}
        
        print(f"[DEBUG] Usando ip-api.com (plan gratuito: 45 requests/minuto)")
        print(f"[DEBUG] URL de request: {url}")
        
        response = requests.get(url, headers=headers, timeout=5)
        
        print(f"[DEBUG] Response status code: {response.status_code}")
        
        # Verificar headers de rate limiting
        x_rl = response.headers.get('X-Rl', 'N/A')
        x_ttl = response.headers.get('X-Ttl', 'N/A')
        print(f"[DEBUG] Rate limit - Requests remaining: {x_rl}, Seconds until reset: {x_ttl}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"[DEBUG] Response data keys: {list(data.keys())}")
            
            if data.get('status') == 'fail':
                error_message = data.get('message', 'Unknown error')
                print(f"❌ Error de ip-api.com: {error_message}")
                print(f"[DEBUG] Error completo: {data}")
                return None
            
            if data.get('status') == 'success' and 'lon' in data and 'lat' in data:
                lon = data['lon']
                lat = data['lat']
                print(f"[DEBUG] ✅ Coordenadas obtenidas: lon={lon}, lat={lat}")
                print(f"[DEBUG] Ciudad: {data.get('city', 'N/A')}, País: {data.get('country', 'N/A')}, Región: {data.get('regionName', 'N/A')}")
                return (lon, lat)
            else:
                print(f"❌ No se encontraron coordenadas en la respuesta o status no es 'success'")
                print(f"[DEBUG] Datos recibidos: {data}")
        elif response.status_code == 429:
            error_data = response.json() if response.text else {}
            print("⚠️  Límite de requests alcanzado en ip-api.com (plan gratuito: 45 requests/minuto)")
            print(f"   Requests restantes: {x_rl}, Segundos hasta reset: {x_ttl}")
            print(f"[DEBUG] Response body: {error_data}")
            # Retornar None para que el sistema pueda usar fallback
        elif response.status_code == 403:
            print("❌ Acceso denegado por ip-api.com")
            print(f"[DEBUG] Response body: {response.text[:200]}")
        else:
            print(f"❌ Error obteniendo coordenadas desde IP: HTTP {response.status_code}")
            print(f"[DEBUG] Response body: {response.text[:200]}")
    except requests.exceptions.Timeout:
        print(f"❌ Timeout al obtener coordenadas desde IP: {ip_address}")
        print(f"[DEBUG] El servicio ip-api.com no respondió en 5 segundos")
    except requests.exceptions.RequestException as e:
        print(f"❌ Error de red al obtener coordenadas desde IP: {e}")
        print(f"[DEBUG] Tipo de error: {type(e).__name__}")
    except Exception as e:
        print(f"❌ Error inesperado obteniendo coordenadas desde IP: {e}")
        print(f"[DEBUG] Tipo de error: {type(e).__name__}")
        import traceback
        print(f"[DEBUG] Traceback: {traceback.format_exc()}")
    
    return None


@locality_detection_bp.route('/detect-locality', methods=['GET', 'POST'])
def detect_locality():
    """
    Detecta la localidad basada en IP o coordenadas proporcionadas.
    
    Query params (GET) o Body (POST):
    - lat: Latitud (opcional si se proporciona IP)
    - lon: Longitud (opcional si se proporciona IP)
    - ip: Dirección IP (opcional si se proporcionan coordenadas)
    
    Si no se proporcionan coordenadas ni IP, intenta obtener la IP del request.
    """
    print(f"[DEBUG] detect_locality: Iniciando - Method: {request.method}")
    
    try:
        # Obtener parámetros
        if request.method == 'POST':
            data = request.get_json() or {}
            lat = data.get('lat')
            lon = data.get('lon')
            ip = data.get('ip')
            print(f"[DEBUG] POST data recibida: lat={lat}, lon={lon}, ip={ip}")
        else:
            lat = request.args.get('lat', type=float)
            lon = request.args.get('lon', type=float)
            ip = request.args.get('ip')
            print(f"[DEBUG] GET params: lat={lat}, lon={lon}, ip={ip}")
        
        # Si no se proporcionan coordenadas, intentar obtenerlas desde IP
        if lat is None or lon is None:
            print(f"[DEBUG] Coordenadas no proporcionadas, intentando obtener desde IP")
            
            if not ip:
                # Obtener IP del request
                if request.headers.getlist("X-Forwarded-For"):
                    # X-Forwarded-For puede contener múltiples IPs separadas por comas
                    ip_header = request.headers.getlist("X-Forwarded-For")[0]
                    # Tomar solo la primera IP (la del cliente original)
                    ip = ip_header.split(',')[0].strip()
                    print(f"[DEBUG] IP obtenida de X-Forwarded-For: {ip} (header completo: {ip_header})")
                elif request.headers.getlist("X-Real-Ip"):
                    ip_header = request.headers.getlist("X-Real-Ip")[0]
                    # Por si acaso también tiene múltiples IPs
                    ip = ip_header.split(',')[0].strip()
                    print(f"[DEBUG] IP obtenida de X-Real-Ip: {ip} (header completo: {ip_header})")
                else:
                    ip = request.remote_addr
                    print(f"[DEBUG] IP obtenida de request.remote_addr: {ip}")
            
            if not ip:
                print(f"❌ No se pudo obtener la IP del request")
                # Intentar usar localidad por defecto
                if Config.DEFAULT_LOCALITY_ID:
                    print(f"[DEBUG] Usando localidad por defecto: {Config.DEFAULT_LOCALITY_ID}")
                    try:
                        import uuid as uuid_lib
                        default_locality_uuid = uuid_lib.UUID(Config.DEFAULT_LOCALITY_ID)
                        locality = Locality.query.get(default_locality_uuid)
                        if locality:
                            print(f"✅ Usando localidad por defecto: {locality.name}")
                            return jsonify({
                                'success': True,
                                'data': {
                                    'locality': locality.to_dict(),
                                    'coordinates': None,
                                    'fallback': 'default_locality'
                                }
                            }), 200
                    except (ValueError, TypeError) as e:
                        print(f"⚠️  DEFAULT_LOCALITY_ID no es un UUID válido: {e}")
                
                # Si no hay localidad por defecto configurada, usar la localidad específica de fallback (Cordoba capital)
                fallback_locality_id = '39acf5ca-28d1-4300-b009-07c675c45073'
                print(f"[DEBUG] Intentando usar localidad de fallback: {fallback_locality_id}")
                try:
                    import uuid as uuid_lib
                    fallback_locality_uuid = uuid_lib.UUID(fallback_locality_id)
                    fallback_locality = Locality.query.get(fallback_locality_uuid)
                    if fallback_locality:
                        print(f"✅ Usando localidad de fallback: {fallback_locality.name}")
                        # Obtener la zona de entrega para la localidad de fallback
                        crm_zone_id = None
                        zone_locality = CrmZoneLocality.query.filter_by(locality_id=fallback_locality.id).first()
                        if zone_locality:
                            crm_zone_id = zone_locality.crm_zone_id
                            print(f"[DEBUG] Zona de entrega encontrada para fallback: crm_zone_id={crm_zone_id}")
                        else:
                            print(f"[DEBUG] ⚠️ No se encontró zona de entrega para localidad de fallback: {fallback_locality.name} (id: {fallback_locality.id})")
                            # Intentar buscar por nombre de localidad en crm_delivery_zones
                            try:
                                crm_zone = CrmDeliveryZone.query.filter(
                                    CrmDeliveryZone.name.ilike(f'%{fallback_locality.name}%'),
                                    CrmDeliveryZone.crm_deleted_at.is_(None)
                                ).first()
                                if crm_zone:
                                    crm_zone_id = crm_zone.crm_zone_id
                                    print(f"[DEBUG] Zona encontrada por nombre para fallback: {crm_zone.name} (crm_zone_id: {crm_zone_id})")
                            except Exception as e:
                                print(f"[DEBUG] Error al buscar zona por nombre para fallback: {str(e)}")
                        
                        response_data = {
                            'locality': fallback_locality.to_dict(),
                            'coordinates': None,
                            'fallback': 'cordoba_capital',
                            'reason': 'No se pudo obtener la IP del request. Usando localidad de fallback (Cordoba capital).'
                        }
                        
                        if crm_zone_id:
                            response_data['crm_zone_id'] = crm_zone_id
                            print(f"[DEBUG] crm_zone_id agregado a respuesta de fallback: {crm_zone_id}")
                        else:
                            print(f"[DEBUG] ⚠️ No se encontró crm_zone_id para localidad de fallback: {fallback_locality.name} (id: {fallback_locality.id})")
                        
                        return jsonify({
                            'success': True,
                            'data': response_data
                        }), 200
                except (ValueError, TypeError) as e:
                    print(f"⚠️  ID de localidad de fallback no es un UUID válido: {e}")
                
                return jsonify({
                    'success': False,
                    'error': 'No se pudo obtener la IP del request y no se proporcionaron coordenadas',
                    'hint': 'Para desarrollo local, puedes usar coordenadas directamente: /api/detect-locality?lat=-31.4201&lon=-64.1888'
                }), 400
            
            print(f"[DEBUG] Obteniendo coordenadas para IP: {ip}")
            
            # Verificar si es IP local
            # Si la IP fue proporcionada explícitamente como parámetro (simulación), intentar geolocalizarla
            # Si es IP local y NO fue proporcionada explícitamente, usar fallback directamente
            ip_was_provided = bool(request.args.get('ip') or (request.method == 'POST' and request.get_json() and request.get_json().get('ip')))
            
            if is_local_ip(ip) and not ip_was_provided:
                print(f"[DEBUG] IP local detectada ({ip}) y no fue proporcionada explícitamente, usando fallback directamente")
                coords = None
            else:
                # Obtener coordenadas desde IP (solo si no es local o si fue proporcionada explícitamente)
                if ip_was_provided:
                    print(f"[DEBUG] IP proporcionada explícitamente ({ip}), intentando geolocalización a través de ip-api.com")
                else:
                    print(f"[DEBUG] IP pública detectada ({ip}), intentando geolocalización a través de ip-api.com")
                coords = get_coordinates_from_ip(ip, force_geolocation=ip_was_provided)
            
            if not coords:
                print(f"❌ No se pudieron obtener coordenadas desde IP: {ip}")
                print(f"[DEBUG] Esto puede deberse a: 1) Límite de requests alcanzado en ip-api.com (45/minuto), 2) IP inválida, 3) Error de red")
                
                # Intentar usar localidad por defecto si está configurada
                if Config.DEFAULT_LOCALITY_ID:
                    print(f"[DEBUG] Intentando usar localidad por defecto: {Config.DEFAULT_LOCALITY_ID}")
                    try:
                        from sqlalchemy.dialects.postgresql import UUID as PG_UUID
                        import uuid as uuid_lib
                        # Intentar convertir a UUID
                        default_locality_uuid = uuid_lib.UUID(Config.DEFAULT_LOCALITY_ID)
                        locality = Locality.query.get(default_locality_uuid)
                        if locality:
                            print(f"✅ Usando localidad por defecto: {locality.name}")
                            return jsonify({
                                'success': True,
                                'data': {
                                    'locality': locality.to_dict(),
                                    'coordinates': None,
                                    'fallback': 'default_locality',
                                    'reason': 'IP local o no se pudieron obtener coordenadas desde IP'
                                }
                            }), 200
                        else:
                            print(f"⚠️  Localidad por defecto no encontrada: {Config.DEFAULT_LOCALITY_ID}")
                    except (ValueError, TypeError) as e:
                        print(f"⚠️  DEFAULT_LOCALITY_ID no es un UUID válido: {e}")
                else:
                    print(f"[DEBUG] DEFAULT_LOCALITY_ID no está configurada en .env")
                
                # Si no hay localidad por defecto, usar la localidad específica de fallback (Cordoba capital)
                fallback_locality_id = '39acf5ca-28d1-4300-b009-07c675c45073'
                print(f"[DEBUG] Intentando usar localidad de fallback: {fallback_locality_id}")
                try:
                    import uuid as uuid_lib
                    fallback_locality_uuid = uuid_lib.UUID(fallback_locality_id)
                    fallback_locality = Locality.query.get(fallback_locality_uuid)
                    if fallback_locality:
                        print(f"✅ Usando localidad de fallback: {fallback_locality.name}")
                        # Obtener la zona de entrega para la localidad de fallback
                        crm_zone_id = None
                        zone_locality = CrmZoneLocality.query.filter_by(locality_id=fallback_locality.id).first()
                        if zone_locality:
                            crm_zone_id = zone_locality.crm_zone_id
                            print(f"[DEBUG] Zona de entrega encontrada para fallback: crm_zone_id={crm_zone_id}")
                        else:
                            print(f"[DEBUG] ⚠️ No se encontró zona de entrega para localidad de fallback: {fallback_locality.name} (id: {fallback_locality.id})")
                            # Intentar buscar por nombre de localidad en crm_delivery_zones
                            try:
                                crm_zone = CrmDeliveryZone.query.filter(
                                    CrmDeliveryZone.name.ilike(f'%{fallback_locality.name}%'),
                                    CrmDeliveryZone.crm_deleted_at.is_(None)
                                ).first()
                                if crm_zone:
                                    crm_zone_id = crm_zone.crm_zone_id
                                    print(f"[DEBUG] Zona encontrada por nombre para fallback: {crm_zone.name} (crm_zone_id: {crm_zone_id})")
                            except Exception as e:
                                print(f"[DEBUG] Error al buscar zona por nombre para fallback: {str(e)}")
                        
                        response_data = {
                            'locality': fallback_locality.to_dict(),
                            'coordinates': None,
                            'fallback': 'cordoba_capital',
                            'reason': 'IP local o no se pudieron obtener coordenadas desde IP. Usando localidad de fallback (Cordoba capital).'
                        }
                        
                        if crm_zone_id:
                            response_data['crm_zone_id'] = crm_zone_id
                            print(f"[DEBUG] crm_zone_id agregado a respuesta de fallback: {crm_zone_id}")
                        else:
                            print(f"[DEBUG] ⚠️ No se encontró crm_zone_id para localidad de fallback: {fallback_locality.name} (id: {fallback_locality.id})")
                        
                        return jsonify({
                            'success': True,
                            'data': response_data
                        }), 200
                    else:
                        print(f"⚠️  Localidad de fallback no encontrada: {fallback_locality_id}")
                except (ValueError, TypeError) as e:
                    print(f"⚠️  ID de localidad de fallback no es un UUID válido: {e}")
                
                # Si el fallback específico no funciona, intentar obtener la primera localidad disponible
                print(f"[DEBUG] Intentando usar la primera localidad disponible como último recurso")
                first_locality = Locality.query.first()
                if first_locality:
                    print(f"✅ Usando primera localidad disponible como último recurso: {first_locality.name}")
                    return jsonify({
                        'success': True,
                        'data': {
                            'locality': first_locality.to_dict(),
                            'coordinates': None,
                            'fallback': 'first_available',
                            'reason': 'IP local o no se pudieron obtener coordenadas desde IP. Usando primera localidad disponible como último recurso.'
                        }
                    }), 200
                
                return jsonify({
                    'success': False,
                    'error': 'No se pudieron obtener las coordenadas desde la IP y no hay localidad por defecto configurada.',
                    'ip': ip,
                    'hint': 'Para desarrollo local, puedes: 1) Agregar DEFAULT_LOCALITY_ID en .env, 2) Usar coordenadas directamente: /api/detect-locality?lat=-31.4201&lon=-64.1888'
                }), 400
            
            lon, lat = coords
            print(f"[DEBUG] Coordenadas obtenidas: lon={lon}, lat={lat}")
        else:
            print(f"[DEBUG] Usando coordenadas proporcionadas: lon={lon}, lat={lat}")
        
        # Buscar localidad por coordenadas
        print(f"[DEBUG] Buscando localidad para coordenadas: lon={lon}, lat={lat}")
        locality = find_locality_by_coordinates(lon, lat)
        
        if not locality:
            print(f"❌ No se encontró localidad para coordenadas: lon={lon}, lat={lat}")
            # Contar cuántas zonas hay
            zone_count = CrmDeliveryZone.query.filter(
                CrmDeliveryZone.crm_deleted_at.is_(None)
            ).count()
            print(f"[DEBUG] Zonas de entrega disponibles: {zone_count}")
            
            # Intentar usar localidad por defecto si está configurada
            if Config.DEFAULT_LOCALITY_ID:
                print(f"[DEBUG] Intentando usar localidad por defecto: {Config.DEFAULT_LOCALITY_ID}")
                try:
                    import uuid as uuid_lib
                    default_locality_uuid = uuid_lib.UUID(Config.DEFAULT_LOCALITY_ID)
                    default_locality = Locality.query.get(default_locality_uuid)
                    if default_locality:
                        print(f"✅ Usando localidad por defecto: {default_locality.name}")
                        return jsonify({
                            'success': True,
                            'data': {
                                'locality': default_locality.to_dict(),
                                'coordinates': {'lon': lon, 'lat': lat},
                                'fallback': 'default_locality',
                                'reason': 'No se encontró localidad para las coordenadas proporcionadas'
                            }
                        }), 200
                except (ValueError, TypeError) as e:
                    print(f"⚠️  DEFAULT_LOCALITY_ID no es un UUID válido: {e}")
            
            # Si no hay localidad por defecto configurada, usar la localidad específica de fallback (Cordoba capital)
            fallback_locality_id = '39acf5ca-28d1-4300-b009-07c675c45073'
            print(f"[DEBUG] Intentando usar localidad de fallback: {fallback_locality_id}")
            try:
                import uuid as uuid_lib
                fallback_locality_uuid = uuid_lib.UUID(fallback_locality_id)
                fallback_locality = Locality.query.get(fallback_locality_uuid)
                if fallback_locality:
                    print(f"✅ Usando localidad de fallback: {fallback_locality.name}")
                    # Obtener la zona de entrega para la localidad de fallback
                    crm_zone_id = None
                    zone_locality = CrmZoneLocality.query.filter_by(locality_id=fallback_locality.id).first()
                    if zone_locality:
                        crm_zone_id = zone_locality.crm_zone_id
                        print(f"[DEBUG] Zona de entrega encontrada para fallback: crm_zone_id={crm_zone_id}")
                    else:
                        print(f"[DEBUG] ⚠️ No se encontró zona de entrega para localidad de fallback: {fallback_locality.name} (id: {fallback_locality.id})")
                        # Intentar buscar por nombre de localidad en crm_delivery_zones
                        try:
                            crm_zone = CrmDeliveryZone.query.filter(
                                CrmDeliveryZone.name.ilike(f'%{fallback_locality.name}%'),
                                CrmDeliveryZone.crm_deleted_at.is_(None)
                            ).first()
                            if crm_zone:
                                crm_zone_id = crm_zone.crm_zone_id
                                print(f"[DEBUG] Zona encontrada por nombre para fallback: {crm_zone.name} (crm_zone_id: {crm_zone_id})")
                        except Exception as e:
                            print(f"[DEBUG] Error al buscar zona por nombre para fallback: {str(e)}")
                    
                    response_data = {
                        'locality': fallback_locality.to_dict(),
                        'coordinates': {'lon': lon, 'lat': lat},
                        'fallback': 'cordoba_capital',
                        'reason': 'No se encontró localidad para las coordenadas proporcionadas. Usando localidad de fallback (Cordoba capital).'
                    }
                    
                    if crm_zone_id:
                        response_data['crm_zone_id'] = crm_zone_id
                        print(f"[DEBUG] crm_zone_id agregado a respuesta de fallback: {crm_zone_id}")
                    else:
                        print(f"[DEBUG] ⚠️ No se encontró crm_zone_id para localidad de fallback: {fallback_locality.name} (id: {fallback_locality.id})")
                    
                    print(f"[DEBUG] Respuesta de fallback: {json.dumps(response_data, indent=2, default=str)}")
                    
                    return jsonify({
                        'success': True,
                        'data': response_data
                    }), 200
                else:
                    print(f"⚠️  Localidad de fallback no encontrada: {fallback_locality_id}")
            except (ValueError, TypeError) as e:
                print(f"⚠️  ID de localidad de fallback no es un UUID válido: {e}")
            
            return jsonify({
                'success': False,
                'error': 'No se encontró una localidad para las coordenadas proporcionadas',
                'coordinates': {'lon': lon, 'lat': lat},
                'hint': 'Verifica que las zonas de entrega estén configuradas correctamente en la base de datos'
            }), 404
        
        print(f"✅ Localidad encontrada: {locality.name} (ID: {locality.id})")
        
        # Obtener la zona de entrega asociada a esta localidad
        crm_zone_id = None
        zone_locality = CrmZoneLocality.query.filter_by(locality_id=locality.id).first()
        if zone_locality:
            crm_zone_id = zone_locality.crm_zone_id
            print(f"[DEBUG] Zona de entrega encontrada: crm_zone_id={crm_zone_id}")
        else:
            print(f"[DEBUG] ⚠️ No se encontró zona de entrega para localidad: {locality.name} (id: {locality.id})")
            # Intentar buscar por nombre de localidad en crm_delivery_zones
            try:
                crm_zone = CrmDeliveryZone.query.filter(
                    CrmDeliveryZone.name.ilike(f'%{locality.name}%'),
                    CrmDeliveryZone.crm_deleted_at.is_(None)
                ).first()
                if crm_zone:
                    crm_zone_id = crm_zone.crm_zone_id
                    print(f"[DEBUG] Zona encontrada por nombre: {crm_zone.name} (crm_zone_id: {crm_zone_id})")
            except Exception as e:
                print(f"[DEBUG] Error al buscar zona por nombre: {str(e)}")
        
        response_data = {
            'locality': locality.to_dict(),
            'coordinates': {'lon': lon, 'lat': lat}
        }
        
        if crm_zone_id:
            response_data['crm_zone_id'] = crm_zone_id
            print(f"[DEBUG] crm_zone_id agregado a respuesta: {crm_zone_id}")
        else:
            print(f"[DEBUG] ⚠️ No se encontró crm_zone_id para localidad: {locality.name} (id: {locality.id})")
        
        print(f"[DEBUG] Respuesta final de detect_locality: {json.dumps(response_data, indent=2, default=str)}")
        
        return jsonify({
            'success': True,
            'data': response_data
        }), 200
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"❌ Error en detect_locality: {str(e)}")
        print(f"[DEBUG] Traceback completo:\n{error_trace}")
        return jsonify({
            'success': False,
            'error': str(e),
            'debug_info': 'Revisa los logs del servidor para más detalles'
        }), 500


@locality_detection_bp.route('/localities', methods=['GET'])
def get_all_localities():
    """
    Obtiene todas las localidades disponibles.
    Útil para la barra de debug.
    """
    try:
        localities = Locality.query.all()
        
        return jsonify({
            'success': True,
            'data': [loc.to_dict() for loc in localities]
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
