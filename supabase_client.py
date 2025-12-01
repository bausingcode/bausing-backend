"""
Cliente de Supabase para manejo de Storage
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Cargar variables de entorno
load_dotenv()

# Configuración de Supabase
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
SUPABASE_PROJECT_ID = 'rymjxnuhyquoajiaxvgs'

# Buckets
PRODUCT_IMAGES_BUCKET = 'product-images'
HERO_IMAGES_BUCKET = 'hero-images'

def get_supabase_client() -> Client:
    """Obtiene el cliente de Supabase"""
    if not SUPABASE_URL:
        raise ValueError("SUPABASE_URL no está configurada en las variables de entorno")
    
    if not SUPABASE_KEY:
        raise ValueError("SUPABASE_KEY no está configurada en las variables de entorno")
    
    return create_client(SUPABASE_URL, SUPABASE_KEY)

