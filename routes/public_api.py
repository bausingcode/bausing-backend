from flask import Blueprint, request, jsonify
from functools import wraps
from config import Config
from database import db
from models.product import Product, ProductVariant, ProductPrice
from models.image import ProductImage
from models.category import Category
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import joinedload

public_api_bp = Blueprint('public_api', __name__)

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
            return jsonify({
                'success': False,
                'error': 'API key requerida.'
            }), 401
        
        if api_key != Config.API_KEY:
            return jsonify({
                'success': False,
                'error': 'API key incorrecta.'
            }), 401
        
        return f(*args, **kwargs)
    
    return decorated_function


@public_api_bp.route('/public/health', methods=['GET'])
@api_key_required
def health_check():
    try:
        from sqlalchemy import text
        db.session.execute(text('SELECT 1'))
        db_status = 'connected'
    except:
        db_status = 'disconnected'
    
    return jsonify({
        'success': True,
        'status': 'healthy',
        'database': db_status,
        'message': 'API funcionando correctamente'
    })

