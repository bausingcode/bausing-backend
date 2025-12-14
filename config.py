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
    
    # Configuración de Resend para emails
    RESEND_API_KEY = os.getenv('RESEND_API_KEY')
    RESEND_FROM_EMAIL = os.getenv('RESEND_FROM_EMAIL', 'noreply@bausing.com')
    
    # Configuración de Frontend URL
    # Si DEBUG_MODE está activado, usar localhost:3000, sino usar FRONTEND_URL del .env
    DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
    if DEBUG_MODE:
        FRONTEND_URL = 'http://localhost:3000'
    else:
        FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')
    
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

