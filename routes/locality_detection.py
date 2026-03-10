from flask import Blueprint, request, jsonify
from database import db
from models.crm_delivery_zone import CrmDeliveryZone, CrmZoneLocality
from models.locality import Locality
from models.catalog import Catalog, LocalityCatalog
from models.address import Address
from routes.auth import verify_token
from models.user import User
from config import Config
import requests
import json
import uuid

locality_detection_bp = Blueprint('locality_detection', __name__)


def point_in_polygon(lon, lat, polygon_coordinates):
    """
    Verifica si un punto (lon, lat) está dentro de un polígono.
    Usa el algoritmo ray casting.
    
    Args:
        lon: Longitud del punto
        lat: Latitud del punto
        polygon_coordinates: Lista de coordenadas [[lon, lat], ...] o [[lon, lat, elevation], ...] del polígono
    
    Returns:
        True si el punto está dentro del polígono, False en caso contrario
    """
    if not polygon_coordinates or len(polygon_coordinates) < 3:
        return False
    
    # Normalizar coordenadas: tomar solo los primeros 2 valores (lon, lat) en caso de que haya elevación
    # También manejar casos donde las coordenadas pueden estar anidadas de manera inesperada
    normalized_coords = []
    for coord in polygon_coordinates:
        try:
            # Si coord es una lista, tomar los primeros 2 elementos
            if isinstance(coord, (list, tuple)):
                if len(coord) >= 2:
                    # Extraer lon y lat, manejando casos donde pueden ser listas anidadas
                    lon_val = coord[0]
                    lat_val = coord[1]
                    
                    # Si lon_val o lat_val son listas, tomar el primer elemento
                    while isinstance(lon_val, (list, tuple)) and len(lon_val) > 0:
                        lon_val = lon_val[0]
                    while isinstance(lat_val, (list, tuple)) and len(lat_val) > 0:
                        lat_val = lat_val[0]
                    
                    # Convertir a float
                    lon_val = float(lon_val)
                    lat_val = float(lat_val)
                    
                    normalized_coords.append([lon_val, lat_val])
                else:
                    return False  # Coordenada inválida
            else:
                return False  # Coordenada no es lista/tupla
        except (ValueError, TypeError, IndexError) as e:
            print(f"[DEBUG] Error normalizando coordenada {coord}: {e}")
            return False  # Error al procesar coordenada
    
    # Asegurarse de que el polígono esté cerrado
    if normalized_coords[0] != normalized_coords[-1]:
        normalized_coords = normalized_coords + [normalized_coords[0]]
    
    n = len(normalized_coords)
    inside = False
    
    j = n - 1
    for i in range(n):
        xi, yi = normalized_coords[i]
        xj, yj = normalized_coords[j]
        
        # Verificar si el rayo cruza el borde
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        
        j = i
    
    return inside


def find_locality_by_coordinates(lon, lat):
    """
    Encuentra la localidad basada en coordenadas geográficas.
    Busca en todas las zonas de entrega y verifica si el punto está dentro de algún polígono.
    Si el punto está dentro de múltiples zonas y alguna empieza con "TERCERIZADO",
    usa esa zona solo para envío y la otra para todo lo demás.
    
    Args:
        lon: Longitud
        lat: Latitud
    
    Returns:
        Tuple (Locality object, shipping_zone_locality) o (None, None) si no se encuentra.
        shipping_zone_locality es el CrmZoneLocality de la zona TERCERIZADO si existe,
        None en caso contrario.
    """
    print(f"[DEBUG] find_locality_by_coordinates: Buscando para lon={lon}, lat={lat}")
    
    # Obtener todas las zonas de entrega activas (no eliminadas)
    zones = CrmDeliveryZone.query.filter(
        CrmDeliveryZone.crm_deleted_at.is_(None)
    ).all()
    
    print(f"[DEBUG] Zonas de entrega encontradas: {len(zones)}")
    
    # Lista para almacenar todas las zonas que contienen el punto
    matching_zones = []
    
    for idx, zone in enumerate(zones):
        # Mostrar todas las zonas para debug (comentado para no saturar logs en producción)
        # print(f"[DEBUG] Procesando zona {idx + 1}/{len(zones)}: {zone.name} (crm_zone_id: {zone.crm_zone_id})")
        
        # Solo mostrar progreso cada 5 zonas para no saturar los logs
        if idx % 5 == 0 or idx == len(zones) - 1:
            print(f"[DEBUG] Procesando zona {idx + 1}/{len(zones)}: {zone.name} (crm_zone_id: {zone.crm_zone_id})")
        
        if not zone.surface_geojson:
            # print(f"[DEBUG] Zona {zone.name} no tiene surface_geojson, saltando")
            continue
        
        # El surface_geojson puede ser una lista de Features o un Feature único
        geojson_data = zone.surface_geojson
        point_in_zone = False
        
        # Si es una lista, iterar sobre cada Feature
        if isinstance(geojson_data, list):
            for feat_idx, feature in enumerate(geojson_data):
                if feature.get('type') == 'Feature' and feature.get('geometry'):
                    geometry = feature['geometry']
                    if geometry.get('type') == 'Polygon':
                        coordinates = geometry.get('coordinates', [])
                        if coordinates and len(coordinates) > 0:
                            # coordinates[0] es el anillo exterior del polígono
                            polygon_coords = coordinates[0]
                            if point_in_polygon(lon, lat, polygon_coords):
                                point_in_zone = True
                                break
                    elif geometry.get('type') == 'MultiPolygon':
                        # Manejar MultiPolygon: iterar sobre cada polígono
                        for polygon_coords_list in geometry.get('coordinates', []):
                            if polygon_coords_list and len(polygon_coords_list) > 0:
                                polygon_coords = polygon_coords_list[0]
                                if point_in_polygon(lon, lat, polygon_coords):
                                    point_in_zone = True
                                    break
                        if point_in_zone:
                            break
        # Si es un Feature único
        elif isinstance(geojson_data, dict):
            if geojson_data.get('type') == 'Feature' and geojson_data.get('geometry'):
                geometry = geojson_data['geometry']
                if geometry.get('type') == 'Polygon':
                    coordinates = geometry.get('coordinates', [])
                    if coordinates and len(coordinates) > 0:
                        polygon_coords = coordinates[0]
                        if point_in_polygon(lon, lat, polygon_coords):
                            point_in_zone = True
                elif geometry.get('type') == 'MultiPolygon':
                    # Manejar MultiPolygon: iterar sobre cada polígono
                    for polygon_coords_list in geometry.get('coordinates', []):
                        if polygon_coords_list and len(polygon_coords_list) > 0:
                            polygon_coords = polygon_coords_list[0]
                            if point_in_polygon(lon, lat, polygon_coords):
                                point_in_zone = True
                                break
        
        if point_in_zone:
            print(f"[DEBUG] ✅ Punto está dentro del polígono de la zona {zone.name} (crm_zone_id: {zone.crm_zone_id})")
            # Encontrar la localidad asociada a esta zona
            zone_locality = CrmZoneLocality.query.filter_by(
                crm_zone_id=zone.crm_zone_id
            ).first()
            
            if zone_locality and zone_locality.locality:
                print(f"[DEBUG] ✅ Zona encontrada: {zone.name} con localidad: {zone_locality.locality.name}")
                matching_zones.append({
                    'zone': zone,
                    'zone_locality': zone_locality,
                    'locality': zone_locality.locality
                })
            else:
                print(f"[DEBUG] ⚠️ Zona {zone.name} contiene el punto pero no tiene localidad asociada")
    
    print(f"[DEBUG] Total de zonas que contienen el punto: {len(matching_zones)}")
    if len(matching_zones) > 0:
        for i, match in enumerate(matching_zones):
            print(f"[DEBUG]   Zona {i+1}: {match['zone'].name} (crm_zone_id: {match['zone'].crm_zone_id})")
    
    if not matching_zones:
        print(f"[DEBUG] ❌ No se encontró ninguna localidad para las coordenadas proporcionadas")
        return (None, None)
    
    # Si hay múltiples zonas, verificar si alguna empieza con "TERCERIZADO"
    if len(matching_zones) > 1:
        print(f"[DEBUG] ⚠️ Punto está dentro de {len(matching_zones)} zonas - Verificando si alguna es TERCERIZADO")
        
        # Buscar zona que empiece con "TERCERIZADO"
        tercerizado_zone = None
        other_zones = []
        
        for match in matching_zones:
            zone_name = match['zone'].name
            zone_name_upper = zone_name.upper().strip()
            print(f"[DEBUG] Verificando zona: '{zone_name}' (upper: '{zone_name_upper}')")
            
            # Verificar si empieza con "TERCERIZADO" (sin importar espacios, acentos, etc.)
            if zone_name_upper.startswith('TERCERIZADO'):
                tercerizado_zone = match
                print(f"[DEBUG] ✅ Zona TERCERIZADO encontrada: {zone_name} (crm_zone_id: {match['zone'].crm_zone_id})")
            else:
                # Agregar todas las zonas no-TERCERIZADO
                other_zones.append(match)
                print(f"[DEBUG] ✅ Zona normal encontrada: {zone_name} (crm_zone_id: {match['zone'].crm_zone_id})")
        
        print(f"[DEBUG] Resumen: {len(other_zones)} zona(s) normal(es), {'1 zona TERCERIZADO' if tercerizado_zone else '0 zonas TERCERIZADO'}")
        
        # Si hay una zona TERCERIZADO y al menos una normal
        if tercerizado_zone and len(other_zones) > 0:
            # Usar la primera zona no-TERCERIZADO para todo lo demás
            other_zone = other_zones[0]
            print(f"[DEBUG] ========================================")
            print(f"[DEBUG] DECISIÓN: Usando zona TERCERIZADO ({tercerizado_zone['zone'].name}) SOLO para envío")
            print(f"[DEBUG] DECISIÓN: Usando zona normal ({other_zone['zone'].name}) para todo lo demás")
            print(f"[DEBUG] ========================================")
            # Retornar la localidad de la zona normal, pero también la zona_locality de TERCERIZADO para envío
            return (other_zone['locality'], tercerizado_zone['zone_locality'])
        elif tercerizado_zone:
            # Solo hay zona TERCERIZADO, usarla normalmente
            print(f"[DEBUG] Solo se encontró zona TERCERIZADO, usándola normalmente")
            return (tercerizado_zone['locality'], None)
        else:
            # Hay múltiples zonas pero ninguna es TERCERIZADO, usar la primera
            print(f"[DEBUG] Múltiples zonas encontradas pero ninguna es TERCERIZADO, usando la primera: {matching_zones[0]['zone'].name}")
            return (matching_zones[0]['locality'], None)
    else:
        # Solo hay una zona
        print(f"[DEBUG] ✅ Una sola zona encontrada: {matching_zones[0]['zone'].name}")
        return (matching_zones[0]['locality'], None)


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


def get_user_from_token():
    """
    Intenta obtener el usuario desde el token de autenticación.
    Retorna el usuario si está autenticado, None en caso contrario.
    """
    try:
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(' ')[1]  # Formato: "Bearer <token>"
            except IndexError:
                return None
        
            if not token:
                return None
            
            payload = verify_token(token)
            if not payload:
                return None
            
            try:
                user_id = uuid.UUID(payload['user_id'])
            except (ValueError, KeyError):
                return None
            
            user = User.query.get(user_id)
            return user
    except Exception as e:
        print(f"[DEBUG] Error al obtener usuario desde token: {str(e)}")
        return None
    
    return None


@locality_detection_bp.route('/detect-locality', methods=['GET', 'POST'])
def detect_locality():
    """
    Detecta la localidad basada en IP o coordenadas proporcionadas.
    Si el usuario está autenticado y tiene direcciones con lat_lon, las usa primero.
    
    Query params (GET) o Body (POST):
    - lat: Latitud (opcional si se proporciona IP o dirección)
    - lon: Longitud (opcional si se proporciona IP o dirección)
    - ip: Dirección IP (opcional si se proporcionan coordenadas o dirección)
    - address_id: ID de dirección a usar (opcional, solo si hay múltiples)
    
    Si no se proporcionan coordenadas ni IP, intenta obtener la IP del request.
    """
    print(f"[DEBUG] detect_locality: Iniciando - Method: {request.method}")
    
    try:
        # Intentar obtener usuario autenticado
        user = get_user_from_token()
        
        # Obtener parámetros
        if request.method == 'POST':
            data = request.get_json() or {}
            lat = data.get('lat')
            lon = data.get('lon')
            ip = data.get('ip')
            address_id = data.get('address_id')
            print(f"[DEBUG] POST data recibida: lat={lat}, lon={lon}, ip={ip}, address_id={address_id}")
        else:
            lat = request.args.get('lat', type=float)
            lon = request.args.get('lon', type=float)
            ip = request.args.get('ip')
            address_id = request.args.get('address_id')
            print(f"[DEBUG] GET params: lat={lat}, lon={lon}, ip={ip}, address_id={address_id}")
        
        # Si el usuario está autenticado y no se proporcionaron coordenadas explícitamente,
        # verificar si tiene direcciones con lat_lon
        if user and lat is None and lon is None:
            print(f"[DEBUG] Usuario autenticado detectado, verificando direcciones con lat_lon")
            addresses_with_coords = Address.query.filter_by(
                user_id=user.id
            ).filter(
                Address.lat_lon.isnot(None),
                Address.lat_lon != ''
            ).all()
            
            if addresses_with_coords:
                print(f"[DEBUG] Usuario tiene {len(addresses_with_coords)} direcciones con coordenadas")
                
                # Si se especificó un address_id, usar esa dirección
                if address_id:
                    try:
                        address_uuid = uuid.UUID(address_id)
                        selected_address = next((a for a in addresses_with_coords if a.id == address_uuid), None)
                        if selected_address:
                            print(f"[DEBUG] Usando dirección especificada: {selected_address.id}")
                            lat_str, lon_str = selected_address.lat_lon.split(',')
                            lat = float(lat_str.strip())
                            lon = float(lon_str.strip())
                            print(f"[DEBUG] Coordenadas de dirección: lat={lat}, lon={lon}")
                        else:
                            print(f"[DEBUG] Dirección especificada no encontrada o sin coordenadas")
                    except (ValueError, AttributeError) as e:
                        print(f"[DEBUG] Error al procesar address_id: {str(e)}")
                
                # Si no se especificó address_id y hay múltiples direcciones, pedir selección
                elif len(addresses_with_coords) > 1:
                    print(f"[DEBUG] Usuario tiene múltiples direcciones, solicitando selección")
                    addresses_data = []
                    for addr in addresses_with_coords:
                        addr_dict = addr.to_dict()
                        # Parsear lat_lon para incluir coordenadas separadas
                        if addr.lat_lon:
                            try:
                                lat_str, lon_str = addr.lat_lon.split(',')
                                addr_dict['coordinates'] = {
                                    'lat': float(lat_str.strip()),
                                    'lon': float(lon_str.strip())
                                }
                            except:
                                pass
                        addresses_data.append(addr_dict)
                    
                    return jsonify({
                        'success': True,
                        'data': {
                            'requires_address_selection': True,
                            'addresses': addresses_data,
                            'message': 'Por favor selecciona una dirección para calcular los precios'
                        }
                    }), 200
                
                # Si hay una sola dirección, usarla automáticamente
                elif len(addresses_with_coords) == 1:
                    selected_address = addresses_with_coords[0]
                    print(f"[DEBUG] Usando única dirección disponible: {selected_address.id}")
                    lat_str, lon_str = selected_address.lat_lon.split(',')
                    lat = float(lat_str.strip())
                    lon = float(lon_str.strip())
                    print(f"[DEBUG] Coordenadas de dirección: lat={lat}, lon={lon}")
        
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
                
                # Si no hay localidad por defecto configurada, usar el catalog de fallback
                fallback_catalog_id = '8335e521-f25a-4f92-8f59-c4439671ef26'
                print(f"[DEBUG] Intentando usar catalog de fallback: {fallback_catalog_id}")
                try:
                    import uuid as uuid_lib
                    fallback_catalog_uuid = uuid_lib.UUID(fallback_catalog_id)
                    fallback_catalog = Catalog.query.get(fallback_catalog_uuid)
                    if fallback_catalog:
                        print(f"✅ Usando catalog de fallback: {fallback_catalog.name}")
                        
                        # Buscar la primera localidad asociada a este catalog
                        locality_assoc = LocalityCatalog.query.filter_by(catalog_id=fallback_catalog.id).first()
                        fallback_locality = locality_assoc.locality if locality_assoc else None
                        
                        response_data = {
                            'catalog': fallback_catalog.to_dict(),
                            'coordinates': None,
                            'fallback': 'catalog',
                            'reason': 'No se pudo obtener la IP del request. Usando catalog de fallback.'
                        }
                        
                        # Incluir localidad si existe (para compatibilidad con frontend)
                        if fallback_locality:
                            response_data['locality'] = fallback_locality.to_dict()
                            print(f"[DEBUG] Localidad asociada al catalog de fallback: {fallback_locality.name}")
                        else:
                            print(f"[DEBUG] ⚠️  El catalog de fallback no tiene localidades asociadas")
                        
                        return jsonify({
                            'success': True,
                            'data': response_data
                        }), 200
                except (ValueError, TypeError) as e:
                    print(f"⚠️  ID de catalog de fallback no es un UUID válido: {e}")
                
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
                
                # Si no hay localidad por defecto, usar el catalog de fallback
                fallback_catalog_id = '8335e521-f25a-4f92-8f59-c4439671ef26'
                print(f"[DEBUG] Intentando usar catalog de fallback: {fallback_catalog_id}")
                try:
                    import uuid as uuid_lib
                    fallback_catalog_uuid = uuid_lib.UUID(fallback_catalog_id)
                    fallback_catalog = Catalog.query.get(fallback_catalog_uuid)
                    if fallback_catalog:
                        print(f"✅ Usando catalog de fallback: {fallback_catalog.name}")
                        
                        # Buscar la primera localidad asociada a este catalog
                        locality_assoc = LocalityCatalog.query.filter_by(catalog_id=fallback_catalog.id).first()
                        fallback_locality = locality_assoc.locality if locality_assoc else None
                        
                        response_data = {
                            'catalog': fallback_catalog.to_dict(),
                            'coordinates': None,
                            'fallback': 'catalog',
                            'reason': 'IP local o no se pudieron obtener coordenadas desde IP. Usando catalog de fallback.'
                        }
                        
                        # Incluir localidad si existe (para compatibilidad con frontend)
                        if fallback_locality:
                            response_data['locality'] = fallback_locality.to_dict()
                            print(f"[DEBUG] Localidad asociada al catalog de fallback: {fallback_locality.name}")
                        else:
                            print(f"[DEBUG] ⚠️  El catalog de fallback no tiene localidades asociadas")
                        
                        return jsonify({
                            'success': True,
                            'data': response_data
                        }), 200
                    else:
                        print(f"⚠️  Catalog de fallback no encontrado: {fallback_catalog_id}")
                except (ValueError, TypeError) as e:
                    print(f"⚠️  ID de catalog de fallback no es un UUID válido: {e}")
                
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
        locality, shipping_zone_locality = find_locality_by_coordinates(lon, lat)
        
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
            
            # Si no hay localidad por defecto configurada, usar el catalog de fallback
            fallback_catalog_id = '8335e521-f25a-4f92-8f59-c4439671ef26'
            print(f"[DEBUG] Intentando usar catalog de fallback: {fallback_catalog_id}")
            try:
                import uuid as uuid_lib
                fallback_catalog_uuid = uuid_lib.UUID(fallback_catalog_id)
                fallback_catalog = Catalog.query.get(fallback_catalog_uuid)
                if fallback_catalog:
                    print(f"✅ Usando catalog de fallback: {fallback_catalog.name}")
                    
                    # Buscar la primera localidad asociada a este catalog
                    locality_assoc = LocalityCatalog.query.filter_by(catalog_id=fallback_catalog.id).first()
                    fallback_locality = locality_assoc.locality if locality_assoc else None
                    
                    response_data = {
                        'catalog': fallback_catalog.to_dict(),
                        'coordinates': {'lon': lon, 'lat': lat},
                        'fallback': 'catalog',
                        'reason': 'No se encontró localidad para las coordenadas proporcionadas. Usando catalog de fallback.'
                    }
                    
                    # Incluir localidad si existe (para compatibilidad con frontend)
                    if fallback_locality:
                        response_data['locality'] = fallback_locality.to_dict()
                        print(f"[DEBUG] Localidad asociada al catalog de fallback: {fallback_locality.name}")
                    else:
                        print(f"[DEBUG] ⚠️  El catalog de fallback no tiene localidades asociadas")
                    
                    print(f"[DEBUG] Respuesta de fallback: {json.dumps(response_data, indent=2, default=str)}")
                    
                    return jsonify({
                        'success': True,
                        'data': response_data
                    }), 200
                else:
                    print(f"⚠️  Catalog de fallback no encontrado: {fallback_catalog_id}")
            except (ValueError, TypeError) as e:
                print(f"⚠️  ID de catalog de fallback no es un UUID válido: {e}")
            
            return jsonify({
                'success': False,
                'error': 'No se encontró una localidad para las coordenadas proporcionadas',
                'coordinates': {'lon': lon, 'lat': lat},
                'hint': 'Verifica que las zonas de entrega estén configuradas correctamente en la base de datos'
            }), 404
        
        print(f"✅ Localidad encontrada: {locality.name} (ID: {locality.id})")
        
        # Obtener la zona de entrega asociada a esta localidad (para todo lo demás, no envío)
        crm_zone_id = None
        is_third_party_transport = False
        shipping_price = None
        
        # Si hay una zona TERCERIZADO para envío, usar esa para calcular envío
        if shipping_zone_locality:
            print(f"[DEBUG] Usando zona TERCERIZADO solo para cálculo de envío")
            is_third_party_transport = shipping_zone_locality.is_third_party_transport or False
            shipping_price = float(shipping_zone_locality.shipping_price) if shipping_zone_locality.shipping_price else None
            print(f"[DEBUG] Envío (zona TERCERIZADO): is_third_party={is_third_party_transport}, shipping_price={shipping_price}")
        
        # Obtener la zona de entrega de la localidad principal (para todo lo demás)
        zone_locality = CrmZoneLocality.query.filter_by(locality_id=locality.id).first()
        
        if zone_locality:
            crm_zone_id = zone_locality.crm_zone_id
            # Solo usar is_third_party_transport y shipping_price de la zona principal si no hay zona TERCERIZADO
            if not shipping_zone_locality:
                is_third_party_transport = zone_locality.is_third_party_transport or False
                shipping_price = float(zone_locality.shipping_price) if zone_locality.shipping_price else None
            print(f"[DEBUG] Zona de entrega principal: crm_zone_id={crm_zone_id}")
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
        
        # Agregar información de transporte tercerizado - SIEMPRE incluir estos campos
        # Si hay zona TERCERIZADO, estos valores vienen de esa zona (solo para envío)
        response_data['is_third_party_transport'] = is_third_party_transport
        if shipping_price is not None:
            response_data['shipping_price'] = shipping_price
        # Si shipping_price es None, no lo agregamos (el frontend lo manejará como null)
        
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

@locality_detection_bp.route('/localities/<uuid:locality_id>/catalog', methods=['GET'])
def get_locality_catalog(locality_id):
    """
    Obtiene el catalog_id asociado a una localidad.
    """
    try:
        import uuid as uuid_lib
        from models.catalog import LocalityCatalog
        
        locality_uuid = uuid_lib.UUID(str(locality_id)) if isinstance(locality_id, str) else locality_id
        locality_catalog = LocalityCatalog.query.filter_by(locality_id=locality_uuid).first()
        
        if locality_catalog:
            return jsonify({
                'success': True,
                'data': {
                    'catalog_id': str(locality_catalog.catalog_id),
                    'locality_id': str(locality_id)
                }
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'No se encontró catálogo asociado a esta localidad'
            }), 404
    except (ValueError, TypeError) as e:
        return jsonify({
            'success': False,
            'error': f'ID de localidad inválido: {str(e)}'
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
