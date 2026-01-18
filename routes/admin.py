from flask import Blueprint, request, jsonify
from database import db
from models.category import Category
from models.product import Product, ProductVariant, ProductPrice
from models.locality import Locality
from models.admin_user import AdminUser, AdminRole
from models.user import User
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
import jwt
import uuid
from datetime import datetime, timedelta
from config import Config
from functools import wraps

admin_bp = Blueprint('admin', __name__)

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
        
        
        # Obtener el usuario admin - convertir string a UUID
        try:
            admin_id = uuid.UUID(payload['admin_id'])
        except (ValueError, KeyError) as e:
            return jsonify({
                'success': False,
                'error': 'ID de usuario inválido'
            }), 401
        
        # Verificar si hay usuarios en la base de datos
        all_users = AdminUser.query.all()
        
        admin_user = AdminUser.query.get(admin_id)
        if not admin_user:
            # Intentar buscar por string también
            admin_user_str = AdminUser.query.filter_by(id=str(admin_id)).first()
            if admin_user_str:
                print(f"DEBUG - Usuario encontrado buscando por string")
                admin_user = admin_user_str
            else:
                return jsonify({
                    'success': False,
                    'error': 'Usuario admin no encontrado'
                }), 401
        
        # Agregar el usuario admin al contexto de la request
        request.admin_user = admin_user
        
        return f(*args, **kwargs)
    
    return decorated_function

@admin_bp.route('/auth/register', methods=['POST'])
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

@admin_bp.route('/auth/login', methods=['POST'])
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

@admin_bp.route('/auth/me', methods=['GET'])
@admin_required
def get_current_user():
    """
    Obtener información del usuario admin actualmente autenticado
    """
    return jsonify({
        'success': True,
        'data': request.admin_user.to_dict()
    }), 200

@admin_bp.route('/auth/roles', methods=['GET'])
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

@admin_bp.route('/products/<uuid:product_id>/complete', methods=['PUT'])
def update_complete_product(product_id):
    """
    Actualizar un producto completo (producto, variantes y precios)
    """
    try:
        product = Product.query.get_or_404(product_id)
        data = request.get_json()
        
        # Actualizar datos básicos del producto
        if 'name' in data:
            product.name = data['name']
        if 'description' in data:
            product.description = data.get('description')
        if 'sku' in data:
            product.sku = data.get('sku')
        if 'category_id' in data or 'subcategory_id' in data:
            category_id = data.get('subcategory_id') or data.get('category_id')
            if category_id:
                category = Category.query.get(category_id)
                if category:
                    product.category_id = category_id
        if 'is_active' in data:
            product.is_active = data.get('is_active')
        
        # Actualizar variantes si se proporcionan
        if 'variants' in data:
            # Opción 1: Eliminar todas las variantes existentes y crear nuevas
            # (Más simple para el admin panel)
            for variant in product.variants:
                db.session.delete(variant)
            
            db.session.flush()
            
            # Crear nuevas variantes
            for variant_data in data['variants']:
                variant = ProductVariant(
                    product_id=product.id,
                    sku=variant_data.get('sku'),
                    price=variant_data.get('price')
                )
                
                db.session.add(variant)
                db.session.flush()
                
                # Crear precios
                for price_data in variant_data.get('prices', []):
                    if price_data.get('locality_id') and price_data.get('price'):
                        locality = Locality.query.get(price_data['locality_id'])
                        if locality:
                            price = ProductPrice(
                                product_variant_id=variant.id,
                                locality_id=price_data['locality_id'],
                                price=price_data['price']
                            )
                            db.session.add(price)
        
        db.session.commit()
        
        # Retornar producto actualizado con todas sus relaciones
        product_data = product.to_dict(include_variants=True)
        
        return jsonify({
            'success': True,
            'data': product_data
        }), 200
        
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

@admin_bp.route('/categories/tree', methods=['GET'])
def get_categories_tree():
    """
    Obtener todas las categorías organizadas en árbol (útil para selects en admin)
    """
    try:
        all_categories = Category.query.all()
        
        # Construir árbol
        category_map = {str(cat.id): cat.to_dict() for cat in all_categories}
        root_categories = []
        
        for cat in all_categories:
            cat_dict = category_map[str(cat.id)]
            if cat.parent_id:
                parent_id_str = str(cat.parent_id)
                if parent_id_str in category_map:
                    if 'children' not in category_map[parent_id_str]:
                        category_map[parent_id_str]['children'] = []
                    category_map[parent_id_str]['children'].append(cat_dict)
            else:
                root_categories.append(cat_dict)
        
        return jsonify({
            'success': True,
            'data': root_categories
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_bp.route('/catalog/summary', methods=['GET'])
def get_catalog_summary():
    """
    Obtener un resumen del catálogo para el dashboard del admin
    """
    try:
        from sqlalchemy import func
        
        total_products = Product.query.count()
        active_products = Product.query.filter_by(is_active=True).count()
        total_categories = Category.query.count()
        total_variants = ProductVariant.query.count()
        total_stock = db.session.query(func.sum(ProductVariant.stock)).scalar() or 0
        
        # Categorías más usadas
        categories_with_count = db.session.query(
            Category.name,
            func.count(Product.id).label('count')
        ).outerjoin(Product, Category.id == Product.category_id).group_by(Category.id, Category.name).limit(5).all()
        
        return jsonify({
            'success': True,
            'data': {
                'total_products': total_products,
                'active_products': active_products,
                'total_categories': total_categories,
                'total_variants': total_variants,
                'total_stock': int(total_stock),
                'top_categories': [
                    {'name': name, 'product_count': count}
                    for name, count in categories_with_count
                ]
            }
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_admin_users():
    """
    Obtener todos los usuarios admin
    """
    try:
        admin_users = AdminUser.query.all()
        return jsonify({
            'success': True,
            'data': [user.to_dict(include_role=True) for user in admin_users]
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_bp.route('/users/<uuid:user_id>', methods=['DELETE'])
@admin_required
def delete_admin_user(user_id):
    """
    Eliminar un usuario admin
    """
    try:
        # No permitir que un usuario se elimine a sí mismo
        if request.admin_user.id == user_id:
            return jsonify({
                'success': False,
                'error': 'No puedes eliminar tu propio usuario'
            }), 400
        
        admin_user = AdminUser.query.get(user_id)
        if not admin_user:
            return jsonify({
                'success': False,
                'error': 'Usuario no encontrado'
            }), 404
        
        db.session.delete(admin_user)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Usuario eliminado correctamente'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_bp.route('/customers', methods=['GET'])
@admin_required
def get_customers():
    """
    Obtener todos los usuarios regulares (clientes) con información de billetera
    """
    try:
        from models.wallet import Wallet
        users = User.query.all()
        results = []
        for user in users:
            user_dict = user.to_dict()
            # Obtener información de la billetera
            wallet = Wallet.query.filter_by(user_id=user.id).first()
            if wallet:
                user_dict['wallet'] = {
                    'balance': float(wallet.balance) if wallet.balance else 0.0,
                    'is_blocked': wallet.is_blocked
                }
            else:
                user_dict['wallet'] = {
                    'balance': 0.0,
                    'is_blocked': False
                }
            results.append(user_dict)
        return jsonify({
            'success': True,
            'data': results
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_bp.route('/customers', methods=['POST'])
@admin_required
def create_customer():
    """
    Crear un nuevo cliente
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400
        
        # Validar campos requeridos
        required_fields = ['email', 'password', 'first_name', 'last_name']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'El campo {field} es requerido'
                }), 400
        
        # Verificar si el email ya existe
        existing_user = User.query.filter_by(email=data['email']).first()
        if existing_user:
            return jsonify({
                'success': False,
                'error': 'Ya existe un usuario con este email'
            }), 400
        
        # Crear nuevo usuario
        new_user = User(
            email=data['email'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            phone=data.get('phone'),
            dni=data.get('dni'),
            email_verified=data.get('email_verified', False),
            is_suspended=data.get('is_suspended', False)
        )
        new_user.set_password(data['password'])
        
        db.session.add(new_user)
        db.session.flush()  # Para obtener el ID del usuario
        
        # Crear billetera automáticamente para el usuario
        from models.wallet import Wallet
        wallet = Wallet(
            user_id=new_user.id,
            balance=0.00,
            is_blocked=False
        )
        db.session.add(wallet)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': new_user.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_bp.route('/customers/<uuid:user_id>/suspend', methods=['PUT'])
@admin_required
def toggle_suspend_customer(user_id):
    """
    Suspender o activar un cliente
    """
    try:
        data = request.get_json()
        is_suspended = data.get('is_suspended')
        
        if is_suspended is None:
            return jsonify({
                'success': False,
                'error': 'El campo is_suspended es requerido'
            }), 400
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'error': 'Usuario no encontrado'
            }), 404
        
        user.is_suspended = bool(is_suspended)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': user.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

