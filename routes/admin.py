from flask import Blueprint, request, jsonify
from database import db
from models.category import Category
from models.product import Product, ProductVariant, ProductPrice
from models.locality import Locality
from models.admin_user import AdminUser, AdminRole
from sqlalchemy.exc import IntegrityError
import jwt
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

@admin_bp.route('/products/complete', methods=['POST'])
def create_complete_product():
    """
    Endpoint para crear un producto completo desde el admin panel.
    Incluye: producto, variantes, stock y precios por localidad en una sola operación.
    
    Body esperado:
    {
        "name": "Nombre del producto",
        "description": "Descripción",
        "sku": "SKU123",
        "category_id": "uuid-categoria",
        "subcategory_id": "uuid-subcategoria",  # opcional
        "is_active": true,
        "variants": [
            {
                "variant_name": "Talle M - Rojo",
                "stock": 10,
                "prices": [
                    {
                        "locality_id": "uuid-localidad",
                        "price": 2999.99
                    }
                ]
            }
        ]
    }
    """
    try:
        data = request.get_json()
        
        if not data or not data.get('name'):
            return jsonify({
                'success': False,
                'error': 'El nombre del producto es requerido'
            }), 400
        
        # Determinar category_id (usar subcategory_id si existe, sino category_id)
        category_id = data.get('subcategory_id') or data.get('category_id')
        
        if not category_id:
            return jsonify({
                'success': False,
                'error': 'category_id o subcategory_id es requerido'
            }), 400
        
        # Verificar que la categoría existe
        category = Category.query.get(category_id)
        if not category:
            return jsonify({
                'success': False,
                'error': 'La categoría especificada no existe'
            }), 400
        
        # Crear el producto
        product = Product(
            name=data['name'],
            description=data.get('description'),
            sku=data.get('sku'),
            category_id=category_id,
            is_active=data.get('is_active', True)
        )
        
        db.session.add(product)
        db.session.flush()  # Para obtener el ID del producto
        
        # Crear variantes con sus precios
        variants_data = data.get('variants', [])
        created_variants = []
        
        for variant_data in variants_data:
            if not variant_data.get('variant_name'):
                db.session.rollback()
                return jsonify({
                    'success': False,
                    'error': 'Cada variante debe tener un variant_name'
                }), 400
            
            # Construir variant_name automáticamente si se proporcionan atributos
            variant_name = variant_data.get('variant_name')
            attributes = variant_data.get('attributes', {})
            
            # Si no hay variant_name pero hay atributos, generar uno
            if not variant_name and attributes:
                parts = []
                if attributes.get('size'):
                    parts.append(attributes['size'])
                if attributes.get('combo'):
                    parts.append(attributes['combo'])
                if attributes.get('model'):
                    parts.append(attributes['model'])
                if attributes.get('color'):
                    parts.append(attributes['color'])
                if attributes.get('dimensions'):
                    parts.append(attributes['dimensions'])
                variant_name = ' - '.join(parts) if parts else 'Variante'
            
            variant = ProductVariant(
                product_id=product.id,
                variant_name=variant_name or 'Variante',
                stock=variant_data.get('stock', 0),
                attributes=attributes if attributes else None
            )
            
            db.session.add(variant)
            db.session.flush()
            
            # Crear precios para cada localidad
            prices_data = variant_data.get('prices', [])
            created_prices = []
            
            for price_data in prices_data:
                if not price_data.get('locality_id') or not price_data.get('price'):
                    continue
                
                # Verificar que la localidad existe
                locality = Locality.query.get(price_data['locality_id'])
                if not locality:
                    continue
                
                price = ProductPrice(
                    product_variant_id=variant.id,
                    locality_id=price_data['locality_id'],
                    price=price_data['price']
                )
                
                db.session.add(price)
                created_prices.append(price.to_dict())
            
            created_variants.append({
                **variant.to_dict(),
                'prices': created_prices
            })
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': {
                **product.to_dict(),
                'variants': created_variants
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
                # Construir variant_name automáticamente si se proporcionan atributos
                variant_name = variant_data.get('variant_name')
                attributes = variant_data.get('attributes', {})
                
                # Si no hay variant_name pero hay atributos, generar uno
                if not variant_name and attributes:
                    parts = []
                    if attributes.get('size'):
                        parts.append(attributes['size'])
                    if attributes.get('combo'):
                        parts.append(attributes['combo'])
                    if attributes.get('model'):
                        parts.append(attributes['model'])
                    if attributes.get('color'):
                        parts.append(attributes['color'])
                    if attributes.get('dimensions'):
                        parts.append(attributes['dimensions'])
                    variant_name = ' - '.join(parts) if parts else 'Variante'
                
                variant = ProductVariant(
                    product_id=product.id,
                    variant_name=variant_name or 'Variante',
                    stock=variant_data.get('stock', 0),
                    attributes=attributes if attributes else None
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

