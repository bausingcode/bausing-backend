import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = os.getenv('SQLALCHEMY_ECHO', 'False').lower() == 'true'
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    API_KEY = os.getenv('API_KEY', 'dev-api-key-change-in-production')
    VENDEDOR_ID = int(os.getenv('VENDEDOR_ID', '1'))
    
    # Configuración de Resend para emails
    RESEND_API_KEY = os.getenv('RESEND_API_KEY')
    RESEND_FROM_EMAIL = os.getenv('RESEND_FROM_EMAIL', 'noreply@bausing.com')
    
    # Configuración de MercadoPago
    MP_ACCESS_TOKEN = os.getenv('MP_ACCESS_TOKEN')
    MP_PUBLIC_KEY = os.getenv('MP_PUBLIC_KEY')  # Opcional, para uso futuro en frontend
    
    # Configuración de geolocalización por IP (ip-api.com)
    # Actualmente usando ip-api.com (plan gratuito: 45 requests/minuto, sin API key requerida)
    # Nota: IPAPI_API_KEY se mantiene por compatibilidad pero no se usa actualmente
    IPAPI_API_KEY = os.getenv('IPAPI_API_KEY', None)
    
    # Localidad por defecto cuando no se puede detectar (UUID de la localidad)
    # Útil para desarrollo o cuando se alcanza el límite de requests
    DEFAULT_LOCALITY_ID = os.getenv('DEFAULT_LOCALITY_ID', None)
    
    # Configuración de Frontend URL
    # Si DEBUG_MODE está activado, usar localhost:3000, sino usar FRONTEND_URL del .env
    DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
    if DEBUG_MODE:
        FRONTEND_URL = 'http://localhost:3000'
    else:
        FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')
    
    # Configuración de Backend URL (para webhooks)
    BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:5000')
    
    # Configuración del pool de conexiones para Supabase
    # Transaction mode (puerto 6543) permite más conexiones que Session mode
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 5,  # Número de conexiones en el pool (Transaction mode permite más)
        'max_overflow': 3,  # Máximo de conexiones adicionales
        'pool_timeout': 20,  # Tiempo de espera para obtener una conexión
        'pool_recycle': 3600,  # Reciclar conexiones después de 1 hora
        'pool_pre_ping': True,  # Verificar que las conexiones estén vivas antes de usarlas
        'connect_args': {
            'connect_timeout': 10,
            'application_name': 'bausing_backend'
        }
    }

