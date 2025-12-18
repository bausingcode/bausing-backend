from flask import Blueprint, request, jsonify
from database import db
from models.user import User
from sqlalchemy.exc import IntegrityError, ProgrammingError, OperationalError
from sqlalchemy import text
from functools import wraps
import jwt
import uuid
import secrets
from datetime import datetime, timedelta
from config import Config
from utils.email_service import email_service

auth_bp = Blueprint('auth', __name__)

def generate_token(user):
    """Genera un token JWT para el usuario"""
    payload = {
        'user_id': str(user.id),
        'email': user.email,
        'exp': datetime.utcnow() + timedelta(days=120), 
        'iat': datetime.utcnow()
    }
    token = jwt.encode(payload, Config.SECRET_KEY, algorithm='HS256')
    return token

def generate_token_from_dict(user_dict):
    """Genera un token JWT desde un diccionario de usuario"""
    payload = {
        'user_id': str(user_dict['id']),
        'email': user_dict['email'],
        'exp': datetime.utcnow() + timedelta(days=120), 
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

def user_required(f):
    """Decorador para proteger rutas que requieren autenticación de usuario"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        
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
        
        # Obtener el usuario
        try:
            user_id = uuid.UUID(payload['user_id'])
        except (ValueError, KeyError):
            return jsonify({
                'success': False,
                'error': 'ID de usuario inválido'
            }), 401
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'error': 'Usuario no encontrado'
            }), 401
        
        # Agregar el usuario al contexto de la request
        request.user = user
        
        return f(*args, **kwargs)
    
    return decorated_function

def generate_verification_token():
    """Genera un token único para verificación de email"""
    return secrets.token_urlsafe(32)

def send_verification_email(user, token):
    """
    Envía un email de verificación al usuario usando el servicio de email.
    """
    verification_url = f"{Config.FRONTEND_URL}/verify-email?token={token}"
    return email_service.send_verification_email(
        user_email=user.email,
        user_first_name=user.first_name,
        verification_url=verification_url
    )

@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Registro de nuevo usuario
    
    Body esperado:
    {
        "email": "user@example.com",
        "password": "password123",
        "first_name": "Juan",
        "last_name": "Pérez",
        "phone": "+5491123456789"
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
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        phone = data.get('phone')
        dni = data.get('dni')
        
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
        
        if not first_name:
            return jsonify({
                'success': False,
                'error': 'El nombre es requerido'
            }), 400
        
        if not last_name:
            return jsonify({
                'success': False,
                'error': 'El apellido es requerido'
            }), 400
        
        # Validar formato de email básico
        if '@' not in email or '.' not in email.split('@')[1]:
            return jsonify({
                'success': False,
                'error': 'El formato del email no es válido'
            }), 400
        
        # Verificar que el email no existe
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({
                'success': False,
                'error': 'El email ya está registrado'
            }), 400
        
        # Generar token de verificación (por ahora solo guardamos en memoria, no en BD)
        verification_token = generate_verification_token()
        verification_expires = datetime.utcnow() + timedelta(days=7)  # Token válido por 7 días
        
        # Crear nuevo usuario
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            dni=dni,
            email_verified=False
            # email_verification_token y email_verification_token_expires se agregarán cuando existan las columnas en la BD
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        # Enviar email de verificación
        try:
            send_verification_email(user, verification_token)
        except Exception as e:
            # No fallar el registro si falla el envío de email
            print(f"Error al enviar email de verificación: {str(e)}")
        
        # Generar token JWT
        token = generate_token(user)
        
        return jsonify({
            'success': True,
            'data': {
                'user': user.to_dict(),
                'token': token,
                'message': 'Usuario registrado correctamente. Se ha enviado un email de verificación.'
            }
        }), 201
        
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Error de integridad: El email ya está registrado'
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Login de usuario
    
    Body esperado:
    {
        "email": "user@example.com",
        "password": "password123"
    }
    
    Nota: El login funciona incluso si el email no está verificado.
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
        
        # Buscar usuario
        try:
            user = User.query.filter_by(email=email).first()
        except (ProgrammingError, OperationalError) as db_error:
            # Si hay un error de base de datos (como columnas faltantes), intentar consulta directa
            print(f"Error de base de datos (columnas faltantes): {str(db_error)}")
            try:
                # Consulta directa solo con columnas básicas
                result = db.session.execute(
                    text("SELECT id, first_name, last_name, email, phone, dni, password_hash, is_suspended, created_at FROM users WHERE email = :email LIMIT 1"),
                    {"email": email}
                ).fetchone()
                
                if not result:
                    return jsonify({
                        'success': False,
                        'error': 'No existe una cuenta con este email'
                    }), 401
                
                # Crear un objeto User manualmente con los datos básicos
                from werkzeug.security import check_password_hash
                if not check_password_hash(result.password_hash, password):
                    return jsonify({
                        'success': False,
                        'error': 'La contraseña es incorrecta'
                    }), 401
                
                # Verificar si el usuario está suspendido
                is_suspended = getattr(result, 'is_suspended', False) if hasattr(result, 'is_suspended') else False
                
                if is_suspended:
                    return jsonify({
                        'success': False,
                        'error': 'Tu cuenta ha sido suspendida. Contacta con el administrador.'
                    }), 403
                
                # Crear respuesta manual
                user_dict = {
                    'id': str(result.id),
                    'first_name': result.first_name,
                    'last_name': result.last_name,
                    'email': result.email,
                    'phone': result.phone,
                    'dni': result.dni,
                    'email_verified': False,  # Por defecto
                    'is_suspended': is_suspended,
                    'created_at': result.created_at.isoformat() if result.created_at else None
                }
                
                token = generate_token_from_dict(user_dict)
                
                return jsonify({
                    'success': True,
                    'data': {
                        'user': user_dict,
                        'token': token,
                        'email_verified': False
                    }
                }), 200
                
            except Exception as e:
                print(f"Error en consulta alternativa: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': 'No existe una cuenta con este email'
                }), 401
        except Exception as e:
            print(f"Error inesperado al buscar usuario: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'No existe una cuenta con este email'
            }), 401
        
        if not user:
            return jsonify({
                'success': False,
                'error': 'No existe una cuenta con este email'
            }), 401
        
        # Verificar si el usuario está suspendido
        is_suspended = getattr(user, 'is_suspended', False)
        if is_suspended:
            return jsonify({
                'success': False,
                'error': 'Tu cuenta ha sido suspendida. Contacta con el administrador.'
            }), 403
        
        # Verificar contraseña
        try:
            if not user.check_password(password):
                return jsonify({
                    'success': False,
                    'error': 'La contraseña es incorrecta'
                }), 401
        except Exception as e:
            print(f"Error al verificar contraseña: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'Error al verificar las credenciales'
            }), 401
        
        # Generar token (sin importar si el email está verificado)
        token = generate_token(user)
        
        # Obtener email_verified de forma segura
        email_verified = getattr(user, 'email_verified', False)
        
        return jsonify({
            'success': True,
            'data': {
                'user': user.to_dict(),
                'token': token,
                'email_verified': email_verified
            }
        }), 200
        
    except Exception as e:
        print(f"Error en login: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Error al iniciar sesión. Por favor, intenta nuevamente.'
        }), 500

@auth_bp.route('/verify-email', methods=['POST'])
def verify_email():
    """
    Verificar email del usuario usando el token
    
    Body esperado:
    {
        "token": "verification-token"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Token requerido'
            }), 400
        
        token = data.get('token')
        
        if not token:
            return jsonify({
                'success': False,
                'error': 'Token de verificación requerido'
            }), 400
        
        # Buscar usuario con este token
        # Por ahora, como las columnas de token no existen, usamos una búsqueda alternativa
        # TODO: Implementar búsqueda por token cuando existan las columnas email_verification_token
        # Por ahora, este endpoint no funcionará hasta que se agreguen las columnas
        return jsonify({
            'success': False,
            'error': 'La verificación de email aún no está disponible. Las columnas necesarias no existen en la base de datos.'
        }), 501
        
        # Código comentado hasta que existan las columnas:
        # user = User.query.filter_by(email_verification_token=token).first()
        # 
        # if not user:
        #     return jsonify({
        #         'success': False,
        #         'error': 'Token de verificación inválido'
        #     }), 400
        # 
        # # Verificar que el token no haya expirado
        # if user.email_verification_token_expires and user.email_verification_token_expires < datetime.utcnow():
        #     return jsonify({
        #         'success': False,
        #         'error': 'El token de verificación ha expirado'
        #     }), 400
        # 
        # # Verificar el email
        # user.email_verified = True
        # user.email_verification_token = None
        # user.email_verification_token_expires = None
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': {
                'user': user.to_dict(),
                'message': 'Email verificado correctamente'
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@auth_bp.route('/resend-verification', methods=['POST'])
@user_required
def resend_verification():
    """
    Reenviar email de verificación
    Requiere autenticación
    """
    try:
        user = request.user
        
        # Si ya está verificado, no hacer nada
        if user.email_verified:
            return jsonify({
                'success': False,
                'error': 'El email ya está verificado'
            }), 400
        
        # Generar nuevo token (por ahora solo en memoria, no se guarda en BD)
        verification_token = generate_verification_token()
        verification_expires = datetime.utcnow() + timedelta(days=7)
        
        # TODO: Guardar token cuando existan las columnas email_verification_token y email_verification_token_expires
        # user.email_verification_token = verification_token
        # user.email_verification_token_expires = verification_expires
        
        db.session.commit()
        
        # Enviar email
        try:
            send_verification_email(user, verification_token)
        except Exception as e:
            print(f"Error al enviar email de verificación: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'Error al enviar el email de verificación'
            }), 500
        
        return jsonify({
            'success': True,
            'message': 'Email de verificación reenviado correctamente'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@auth_bp.route('/me', methods=['GET'])
@user_required
def get_current_user():
    """
    Obtener información del usuario actualmente autenticado
    """
    return jsonify({
        'success': True,
        'data': request.user.to_dict()
    }), 200

