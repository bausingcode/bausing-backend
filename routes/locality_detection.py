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
    
    # Obtener todas las zonas de entrega activas (no eliminadas)
    zones = CrmDeliveryZone.query.filter(
        CrmDeliveryZone.crm_deleted_at.is_(None)
    ).all()
    
    
    # Lista para almacenar todas las zonas que contienen el punto
    matching_zones = []
    
    for idx, zone in enumerate(zones):
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
            # Encontrar la localidad asociada a esta zona
            zone_locality = CrmZoneLocality.query.filter_by(
                crm_zone_id=zone.crm_zone_id
            ).first()
            
            if zone_locality and zone_locality.locality:
                matching_zones.append({
                    'zone': zone,
                    'zone_locality': zone_locality,
                    'locality': zone_locality.locality
                })
    
    if not matching_zones:
        return (None, None)
    
    # Si hay múltiples zonas, verificar si alguna empieza con "TERCERIZADO"
    if len(matching_zones) > 1:
        
        # Buscar zona que empiece con "TERCERIZADO"
        tercerizado_zone = None
        other_zones = []
        
        for match in matching_zones:
            zone_name = match['zone'].name
            zone_name_upper = zone_name.upper().strip()
            
            # Verificar si empieza con "TERCERIZADO" (sin importar espacios, acentos, etc.)
            if zone_name_upper.startswith('TERCERIZADO'):
                tercerizado_zone = match
            else:
                # Agregar todas las zonas no-TERCERIZADO
                other_zones.append(match)
        
        
        # Si hay una zona TERCERIZADO y al menos una normal
        if tercerizado_zone and len(other_zones) > 0:
            # Usar la primera zona no-TERCERIZADO para todo lo demás
            other_zone = other_zones[0]
            # Retornar la localidad de la zona normal, pero también la zona_locality de TERCERIZADO para envío
            return (other_zone['locality'], tercerizado_zone['zone_locality'])
        elif tercerizado_zone:
            # Solo hay zona TERCERIZADO, usarla normalmente
            return (tercerizado_zone['locality'], None)
        else:
            # Hay múltiples zonas pero ninguna es TERCERIZADO, usar la primera
            return (matching_zones[0]['locality'], None)
    else:
        # Solo hay una zona
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
    
    if is_local_ip(ip_address) and not force_geolocation:
        return None

    try:
        url = f'http://ip-api.com/json/{ip_address}'
        response = requests.get(url, headers={}, timeout=5)

        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'fail':
                return None
            if data.get('status') == 'success' and 'lon' in data and 'lat' in data:
                return (data['lon'], data['lat'])
            return None
    except requests.exceptions.Timeout:
        pass
    except requests.exceptions.RequestException:
        pass
    except Exception:
        pass

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
        else:
            lat = request.args.get('lat', type=float)
            lon = request.args.get('lon', type=float)
            ip = request.args.get('ip')
            address_id = request.args.get('address_id')
        
        # Si el usuario está autenticado y no se proporcionaron coordenadas explícitamente,
        # verificar si tiene direcciones con lat_lon
        if user and lat is None and lon is None:
            addresses_with_coords = Address.query.filter_by(
                user_id=user.id
            ).filter(
                Address.lat_lon.isnot(None),
                Address.lat_lon != ''
            ).all()
            
            if addresses_with_coords:
                
                # Si se especificó un address_id, usar esa dirección
                if address_id:
                    try:
                        address_uuid = uuid.UUID(address_id)
                        selected_address = next((a for a in addresses_with_coords if a.id == address_uuid), None)
                        if selected_address:
                            lat_str, lon_str = selected_address.lat_lon.split(',')
                            lat = float(lat_str.strip())
                            lon = float(lon_str.strip())
                    except (ValueError, AttributeError):
                        pass
                
                # Si no se especificó address_id y hay múltiples direcciones, pedir selección
                elif len(addresses_with_coords) > 1:
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
                    lat_str, lon_str = selected_address.lat_lon.split(',')
                    lat = float(lat_str.strip())
                    lon = float(lon_str.strip())
        
        # Si no se proporcionan coordenadas, intentar obtenerlas desde IP
        if lat is None or lon is None:
            
            if not ip:
                # Obtener IP del request
                if request.headers.getlist("X-Forwarded-For"):
                    # X-Forwarded-For puede contener múltiples IPs separadas por comas
                    ip_header = request.headers.getlist("X-Forwarded-For")[0]
                    # Tomar solo la primera IP (la del cliente original)
                    ip = ip_header.split(',')[0].strip()
                elif request.headers.getlist("X-Real-Ip"):
                    ip_header = request.headers.getlist("X-Real-Ip")[0]
                    # Por si acaso también tiene múltiples IPs
                    ip = ip_header.split(',')[0].strip()
                else:
                    ip = request.remote_addr
            
            if not ip:
                # Intentar usar localidad por defecto
                if Config.DEFAULT_LOCALITY_ID:
                    try:
                        import uuid as uuid_lib
                        default_locality_uuid = uuid_lib.UUID(Config.DEFAULT_LOCALITY_ID)
                        locality = Locality.query.get(default_locality_uuid)
                        if locality:
                            return jsonify({
                                'success': True,
                                'data': {
                                    'locality': locality.to_dict(),
                                    'coordinates': None,
                                    'fallback': 'default_locality'
                                }
                            }), 200
                    except (ValueError, TypeError):
                        pass
                
                # Si no hay localidad por defecto configurada, usar el catalog de fallback
                fallback_catalog_id = '8335e521-f25a-4f92-8f59-c4439671ef26'
                try:
                    import uuid as uuid_lib
                    fallback_catalog_uuid = uuid_lib.UUID(fallback_catalog_id)
                    fallback_catalog = Catalog.query.get(fallback_catalog_uuid)
                    if fallback_catalog:
                        
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
                        
                        return jsonify({
                            'success': True,
                            'data': response_data
                        }), 200
                except (ValueError, TypeError):
                    pass
                
                return jsonify({
                    'success': False,
                    'error': 'No se pudo obtener la IP del request y no se proporcionaron coordenadas',
                    'hint': 'Para desarrollo local, puedes usar coordenadas directamente: /api/detect-locality?lat=-31.4201&lon=-64.1888'
                }), 400
            
            
            # Verificar si es IP local
            # Si la IP fue proporcionada explícitamente como parámetro (simulación), intentar geolocalizarla
            # Si es IP local y NO fue proporcionada explícitamente, usar fallback directamente
            ip_was_provided = bool(request.args.get('ip') or (request.method == 'POST' and request.get_json() and request.get_json().get('ip')))
            
            if is_local_ip(ip) and not ip_was_provided:
                coords = None
            else:
                coords = get_coordinates_from_ip(ip, force_geolocation=ip_was_provided)
            
            if not coords:
                
                # Intentar usar localidad por defecto si está configurada
                if Config.DEFAULT_LOCALITY_ID:
                    try:
                        from sqlalchemy.dialects.postgresql import UUID as PG_UUID
                        import uuid as uuid_lib
                        # Intentar convertir a UUID
                        default_locality_uuid = uuid_lib.UUID(Config.DEFAULT_LOCALITY_ID)
                        locality = Locality.query.get(default_locality_uuid)
                        if locality:
                            return jsonify({
                                'success': True,
                                'data': {
                                    'locality': locality.to_dict(),
                                    'coordinates': None,
                                    'fallback': 'default_locality',
                                    'reason': 'IP local o no se pudieron obtener coordenadas desde IP'
                                }
                            }), 200
                    except (ValueError, TypeError):
                        pass
                
                # Si no hay localidad por defecto, usar el catalog de fallback
                fallback_catalog_id = '8335e521-f25a-4f92-8f59-c4439671ef26'
                try:
                    import uuid as uuid_lib
                    fallback_catalog_uuid = uuid_lib.UUID(fallback_catalog_id)
                    fallback_catalog = Catalog.query.get(fallback_catalog_uuid)
                    if fallback_catalog:
                        
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
                        
                        return jsonify({
                            'success': True,
                            'data': response_data
                        }), 200
                except (ValueError, TypeError):
                    pass
                
                # Si el fallback específico no funciona, intentar obtener la primera localidad disponible
                first_locality = Locality.query.first()
                if first_locality:
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
        
        # Buscar localidad por coordenadas
        locality, shipping_zone_locality = find_locality_by_coordinates(lon, lat)
        
        if not locality:
            # Intentar usar localidad por defecto si está configurada
            if Config.DEFAULT_LOCALITY_ID:
                try:
                    import uuid as uuid_lib
                    default_locality_uuid = uuid_lib.UUID(Config.DEFAULT_LOCALITY_ID)
                    default_locality = Locality.query.get(default_locality_uuid)
                    if default_locality:
                        return jsonify({
                            'success': True,
                            'data': {
                                'locality': default_locality.to_dict(),
                                'coordinates': {'lon': lon, 'lat': lat},
                                'fallback': 'default_locality',
                                'reason': 'No se encontró localidad para las coordenadas proporcionadas'
                            }
                        }), 200
                except (ValueError, TypeError):
                    pass
            
            # Si no hay localidad por defecto configurada, usar el catalog de fallback
            fallback_catalog_id = '8335e521-f25a-4f92-8f59-c4439671ef26'
            try:
                import uuid as uuid_lib
                fallback_catalog_uuid = uuid_lib.UUID(fallback_catalog_id)
                fallback_catalog = Catalog.query.get(fallback_catalog_uuid)
                if fallback_catalog:
                    
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
                    
                    return jsonify({
                        'success': True,
                        'data': response_data
                    }), 200
            except (ValueError, TypeError):
                pass
            
            return jsonify({
                'success': False,
                'error': 'No se encontró una localidad para las coordenadas proporcionadas',
                'coordinates': {'lon': lon, 'lat': lat},
                'hint': 'Verifica que las zonas de entrega estén configuradas correctamente en la base de datos'
            }), 404
        
        
        # Obtener la zona de entrega asociada a esta localidad (para todo lo demás, no envío)
        crm_zone_id = None
        is_third_party_transport = False
        shipping_price = None
        
        # Si hay una zona TERCERIZADO para envío, usar esa para calcular envío
        if shipping_zone_locality:
            is_third_party_transport = shipping_zone_locality.is_third_party_transport or False
            shipping_price = float(shipping_zone_locality.shipping_price) if shipping_zone_locality.shipping_price else None
        
        # Obtener la zona de entrega de la localidad principal (para todo lo demás)
        zone_locality = CrmZoneLocality.query.filter_by(locality_id=locality.id).first()
        
        if zone_locality:
            crm_zone_id = zone_locality.crm_zone_id
            # Solo usar is_third_party_transport y shipping_price de la zona principal si no hay zona TERCERIZADO
            if not shipping_zone_locality:
                is_third_party_transport = zone_locality.is_third_party_transport or False
                shipping_price = float(zone_locality.shipping_price) if zone_locality.shipping_price else None
        else:
            # Intentar buscar por nombre de localidad en crm_delivery_zones
            try:
                crm_zone = CrmDeliveryZone.query.filter(
                    CrmDeliveryZone.name.ilike(f'%{locality.name}%'),
                    CrmDeliveryZone.crm_deleted_at.is_(None)
                ).first()
                if crm_zone:
                    crm_zone_id = crm_zone.crm_zone_id
            except Exception:
                pass
        
        response_data = {
            'locality': locality.to_dict(),
            'coordinates': {'lon': lon, 'lat': lat}
        }
        
        if crm_zone_id:
            response_data['crm_zone_id'] = crm_zone_id
        
        # Agregar información de transporte tercerizado - SIEMPRE incluir estos campos
        # Si hay zona TERCERIZADO, estos valores vienen de esa zona (solo para envío)
        response_data['is_third_party_transport'] = is_third_party_transport
        if shipping_price is not None:
            response_data['shipping_price'] = shipping_price
        # Si shipping_price es None, no lo agregamos (el frontend lo manejará como null)
        
        
        return jsonify({
            'success': True,
            'data': response_data
        }), 200
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
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
