from flask import Blueprint, request, jsonify, current_app
from database import db
from models.image import ProductImage, HeroImage
from sqlalchemy.exc import IntegrityError
from routes.admin import admin_required

images_bp = Blueprint('images', __name__)


def _try_delete_supabase_hero_file(image_url):
    """Elimina un objeto del bucket hero-images a partir de la URL pública (best-effort)."""
    if not image_url:
        return
    try:
        import os
        import re
        import ssl
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError

        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        bucket = 'hero-images'
        if not supabase_url or not supabase_key:
            return
        match = re.search(r'/hero-images/(.+)$', image_url)
        if not match:
            return
        file_path = match.group(1)
        delete_url = f"{supabase_url}/storage/v1/object/{bucket}/{file_path}"
        req = Request(
            delete_url,
            method='DELETE',
            headers={
                "Authorization": f"Bearer {supabase_key}",
                "apikey": supabase_key
            }
        )
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        try:
            with urlopen(req, context=ssl_context) as response:
                if response.status not in [200, 204]:
                    pass
        except HTTPError as e:
            if e.code not in [200, 204]:
                pass
    except Exception:
        pass


# ==================== PRODUCT IMAGES ====================

@images_bp.route('/products/<uuid:product_id>/images', methods=['POST'])
@admin_required
def upload_product_image(product_id):
    """
    Subir imagen de producto (requiere token admin)
    
    Body esperado:
    {
        "image_url": "https://...",
        "alt_text": "Descripción de la imagen",
        "position": 0
    }
    """
    try:
        data = request.get_json()
        
        if not data or not data.get('image_url'):
            return jsonify({
                'success': False,
                'error': 'image_url es requerido'
            }), 400
        
        # Verificar que el producto existe
        from models.product import Product
        product = Product.query.get(product_id)
        if not product:
            return jsonify({
                'success': False,
                'error': 'Producto no encontrado'
            }), 404
        
        image = ProductImage(
            product_id=product_id,
            image_url=data['image_url'],
            alt_text=data.get('alt_text'),
            position=data.get('position', 0)
        )
        
        db.session.add(image)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': image.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@images_bp.route('/products/<uuid:product_id>/images', methods=['GET'])
def get_product_images(product_id):
    """
    Obtener todas las imágenes de un producto
    """
    try:
        images = ProductImage.query.filter_by(product_id=product_id).order_by(ProductImage.position).all()
        
        return jsonify({
            'success': True,
            'data': [img.to_dict() for img in images]
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@images_bp.route('/products/images/<uuid:image_id>', methods=['PUT'])
@admin_required
def update_product_image(image_id):
    """
    Actualizar imagen de producto (requiere token admin)
    
    Body esperado:
    {
        "alt_text": "Nueva descripción",
        "position": 1
    }
    """
    try:
        image = ProductImage.query.get_or_404(image_id)
        data = request.get_json()
        
        if data.get('alt_text') is not None:
            image.alt_text = data['alt_text']
        if data.get('position') is not None:
            image.position = data['position']
        if data.get('image_url'):
            image.image_url = data['image_url']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': image.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@images_bp.route('/products/images/<uuid:image_id>', methods=['DELETE'])
@admin_required
def delete_product_image(image_id):
    """
    Eliminar imagen de producto (requiere token admin)
    """
    try:
        image = ProductImage.query.get_or_404(image_id)
        
        db.session.delete(image)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Imagen eliminada correctamente'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ==================== HERO IMAGES ====================

@images_bp.route('/hero-images', methods=['POST'])
@admin_required
def upload_hero_image():
    """
    Subir hero image (requiere token admin)
    
    Body esperado:
    {
        "image_url": "https://...",
        "title": "Título",
        "subtitle": "Subtítulo",
        "cta_text": "Texto del botón",
        "cta_link": "https://...",
        "position": 0,
        "is_active": true,
        "image_url_mobile": "https://... (opcional, solo móvil)"
    }
    """
    try:
        data = request.get_json()
        
        if not data or not data.get('image_url'):
            return jsonify({
                'success': False,
                'error': 'image_url es requerido'
            }), 400
        
        mobile_raw = data.get('image_url_mobile')
        image_url_mobile = None if mobile_raw in (None, '') else mobile_raw

        hero_image = HeroImage(
            image_url=data['image_url'],
            image_url_mobile=image_url_mobile,
            title=data.get('title'),
            subtitle=data.get('subtitle'),
            cta_text=data.get('cta_text'),
            cta_link=data.get('cta_link'),
            position=data.get('position', 0),
            is_active=data.get('is_active', True)
        )
        
        db.session.add(hero_image)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': hero_image.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@images_bp.route('/hero-images', methods=['GET'])
def get_hero_images():
    """
    Listar hero images
    Query params:
    - position: 1 (hero), 2 (info), 3 (discount), 4 (product banner), 5 (local page), 6 (video) para filtrar por posición.
      Cada ítem puede incluir image_url_mobile (imagen vertical opcional solo para móvil en position 1).
    - active: true/false para filtrar solo activas
    """
    try:
        position_filter = request.args.get('position', type=int)
        active_only = request.args.get('active', 'false').lower() == 'true'
        
        query = HeroImage.query
        if position_filter is not None:
            query = query.filter_by(position=position_filter)
        if active_only:
            query = query.filter_by(is_active=True)
        
        hero_images = query.order_by(
            HeroImage.position, HeroImage.created_at.asc()
        ).all()
        
        return jsonify({
            'success': True,
            'data': [img.to_dict() for img in hero_images]
        }), 200
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': error_trace if current_app.config.get('DEBUG', False) else None
        }), 500

@images_bp.route('/hero-images/<uuid:image_id>', methods=['GET'])
def get_hero_image(image_id):
    """
    Obtener hero image específica
    """
    try:
        hero_image = HeroImage.query.get_or_404(image_id)
        
        return jsonify({
            'success': True,
            'data': hero_image.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@images_bp.route('/hero-images/<uuid:image_id>', methods=['PUT'])
@admin_required
def update_hero_image(image_id):
    """
    Actualizar hero image (requiere token admin)
    """
    try:
        hero_image = HeroImage.query.get_or_404(image_id)
        data = request.get_json()
        
        if data.get('image_url'):
            new_main = data['image_url']
            if hero_image.image_url and hero_image.image_url != new_main:
                _try_delete_supabase_hero_file(hero_image.image_url)
            hero_image.image_url = new_main
        if 'image_url_mobile' in data:
            raw = data.get('image_url_mobile')
            new_mobile = None if raw in (None, '') else raw
            old_mobile = hero_image.image_url_mobile
            if old_mobile and old_mobile != new_mobile:
                _try_delete_supabase_hero_file(old_mobile)
            hero_image.image_url_mobile = new_mobile
        if data.get('title') is not None:
            hero_image.title = data['title']
        if data.get('subtitle') is not None:
            hero_image.subtitle = data['subtitle']
        if data.get('cta_text') is not None:
            hero_image.cta_text = data['cta_text']
        if data.get('cta_link') is not None:
            hero_image.cta_link = data['cta_link']
        if data.get('position') is not None:
            hero_image.position = data['position']
        if data.get('is_active') is not None:
            hero_image.is_active = data['is_active']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': hero_image.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@images_bp.route('/hero-images/<uuid:image_id>', methods=['DELETE'])
@admin_required
def delete_hero_image(image_id):
    """
    Eliminar hero image (requiere token admin)
    También elimina el archivo de Supabase Storage
    """
    try:
        hero_image = HeroImage.query.get_or_404(image_id)
        _try_delete_supabase_hero_file(hero_image.image_url)
        _try_delete_supabase_hero_file(hero_image.image_url_mobile)
        
        # Eliminar el registro de la base de datos
        db.session.delete(hero_image)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Hero image eliminada correctamente'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

