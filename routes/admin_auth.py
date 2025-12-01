from flask import Blueprint, request, jsonify
from database import db
from models.admin_user import AdminUser, AdminRole
from sqlalchemy.exc import IntegrityError
from functools import wraps
import jwt
from datetime import datetime, timedelta
from config import Config

admin_auth_bp = Blueprint('admin_auth', __name__)

def generate_token(admin_user):
    """Genera un token JWT para el usuario admin"""
    payload = {
        'admin_id': str(admin_user.id),
        'email': admin_user.email,
        'role_id': str(admin_user.role_id),
        'exp': datetime.utcnow() + timedelta(days=7),  # Token válido por 7 días
        'iat': datetime.utcnow()
    }
    token = jwt.encode(payload, Config.SECRET_KEY, algorithm='HS256')
    return token

def verify_token(token):
    """Verifica y decodifica un token JWT"""
    try:
        payload = jwt.decode(token, Config.SECRET_KEY, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def admin_required(f):
    """Decorador para proteger rutas que requieren autenticación admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        
        # Buscar token en el header Authorization
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(' ')[1]  # Formato: "Bearer <token>"
            except IndexError:
                return jsonify({
                    'success': False,
                    'error': 'Token inválido'
                }), 401
        
        if not token:
            return jsonify({
                'success': False,
                'error': 'Token de autenticación requerido'
            }), 401
        
        payload = verify_token(token)
        if not payload:
            return jsonify({
                'success': False,
                'error': 'Token inválido o expirado'
            }), 401
        
        # Obtener el usuario admin
        admin_user = AdminUser.query.get(payload['admin_id'])
        if not admin_user:
            return jsonify({
                'success': False,
                'error': 'Usuario admin no encontrado'
            }), 401
        
        # Agregar el usuario admin al contexto de la request
        request.admin_user = admin_user
        
        return f(*args, **kwargs)
    
    return decorated_function

@admin_auth_bp.route('/register', methods=['POST'])
def register():
    """
    Registro de nuevo usuario admin
    
    Body esperado:
    {
        "email": "admin@example.com",
        "password": "password123",
        "role_id": "uuid-role-id"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400
        
        email = data.get('email')
        password = data.get('password')
        role_id = data.get('role_id')
        
        # Validaciones
        if not email:
            return jsonify({
                'success': False,
                'error': 'El email es requerido'
            }), 400
        
        if not password:
            return jsonify({
                'success': False,
                'error': 'La contraseña es requerida'
            }), 400
        
        if not role_id:
            return jsonify({
                'success': False,
                'error': 'El role_id es requerido'
            }), 400
        
        # Verificar que el rol existe
        role = AdminRole.query.get(role_id)
        if not role:
            return jsonify({
                'success': False,
                'error': 'El rol especificado no existe'
            }), 400
        
        # Verificar que el email no existe
        existing_user = AdminUser.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({
                'success': False,
                'error': 'El email ya está registrado'
            }), 400
        
        # Crear nuevo usuario admin
        admin_user = AdminUser(
            email=email,
            role_id=role_id
        )
        admin_user.set_password(password)
        
        db.session.add(admin_user)
        db.session.commit()
        
        # Generar token
        token = generate_token(admin_user)
        
        return jsonify({
            'success': True,
            'data': {
                'admin_user': admin_user.to_dict(),
                'token': token
            }
        }), 201
        
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Error de integridad: ' + str(e)
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_auth_bp.route('/login', methods=['POST'])
def login():
    """
    Login de usuario admin
    
    Body esperado:
    {
        "email": "admin@example.com",
        "password": "password123"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400
        
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({
                'success': False,
                'error': 'Email y contraseña son requeridos'
            }), 400
        
        # Buscar usuario admin
        admin_user = AdminUser.query.filter_by(email=email).first()
        
        if not admin_user or not admin_user.check_password(password):
            return jsonify({
                'success': False,
                'error': 'Credenciales inválidas'
            }), 401
        
        # Generar token
        token = generate_token(admin_user)
        
        return jsonify({
            'success': True,
            'data': {
                'admin_user': admin_user.to_dict(),
                'token': token
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_auth_bp.route('/me', methods=['GET'])
@admin_required
def get_current_user():
    """
    Obtener información del usuario admin actualmente autenticado
    """
    return jsonify({
        'success': True,
        'data': request.admin_user.to_dict()
    }), 200

@admin_auth_bp.route('/roles', methods=['GET'])
def get_roles():
    """
    Obtener todos los roles disponibles
    """
    try:
        roles = AdminRole.query.all()
        return jsonify({
            'success': True,
            'data': [role.to_dict() for role in roles]
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

