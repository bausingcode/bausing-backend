from flask import Blueprint, request, jsonify
from database import db
from models.blog import BlogPost, BlogPostKeyword, BlogPostImage
from models.admin_user import AdminUser
from routes.admin import admin_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from datetime import datetime
import uuid
import re

blog_bp = Blueprint('blog', __name__)

def generate_slug(title):
    """Genera un slug a partir del título"""
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug

@blog_bp.route('', methods=['GET'])
def get_blog_posts():
    """Obtener todos los posts del blog"""
    try:
        status = request.args.get('status')
        include_keywords = request.args.get('include_keywords', 'true').lower() == 'true'
        include_images = request.args.get('include_images', 'true').lower() == 'true'
        
        query = BlogPost.query
        
        if status:
            query = query.filter_by(status=status)
        
        posts = query.order_by(BlogPost.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'data': [post.to_dict(include_keywords=include_keywords, include_images=include_images) for post in posts]
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@blog_bp.route('/<uuid:post_id>', methods=['GET'])
def get_blog_post(post_id):
    """Obtener un post por ID"""
    try:
        include_keywords = request.args.get('include_keywords', 'true').lower() == 'true'
        include_images = request.args.get('include_images', 'true').lower() == 'true'
        post = BlogPost.query.get_or_404(post_id)
        
        return jsonify({
            'success': True,
            'data': post.to_dict(include_keywords=include_keywords, include_images=include_images)
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

@blog_bp.route('/slug/<slug>', methods=['GET'])
def get_blog_post_by_slug(slug):
    """Obtener un post por slug"""
    try:
        include_keywords = request.args.get('include_keywords', 'true').lower() == 'true'
        include_images = request.args.get('include_images', 'true').lower() == 'true'
        post = BlogPost.query.filter_by(slug=slug).first_or_404()
        
        # Incrementar contador de vistas
        post.view_count += 1
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': post.to_dict(include_keywords=include_keywords, include_images=include_images)
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

@blog_bp.route('', methods=['POST'])
@admin_required
def create_blog_post():
    """Crear un nuevo post del blog"""
    try:
        data = request.get_json()
        
        # Obtener el admin user del token
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(' ')[1]
            except:
                pass
        
        if not token:
            return jsonify({
                'success': False,
                'error': 'Token no proporcionado'
            }), 401
        
        from routes.admin import verify_token
        payload = verify_token(token)
        if not payload:
            return jsonify({
                'success': False,
                'error': 'Token inválido'
            }), 401
        
        author_id = uuid.UUID(payload['admin_id'])
        
        if not data or not data.get('title'):
            return jsonify({
                'success': False,
                'error': 'El título es requerido'
            }), 400
        
        # Generar slug si no se proporciona
        slug = data.get('slug') or generate_slug(data['title'])
        
        # Verificar que el slug sea único
        existing_post = BlogPost.query.filter_by(slug=slug).first()
        if existing_post:
            # Agregar número al slug si ya existe
            counter = 1
            while BlogPost.query.filter_by(slug=f"{slug}-{counter}").first():
                counter += 1
            slug = f"{slug}-{counter}"
        
        # Parsear published_at si existe
        published_at = None
        if data.get('published_at'):
            try:
                published_at = datetime.fromisoformat(data['published_at'].replace('Z', '+00:00'))
            except:
                pass
        
        # Si el status es 'published' y no hay published_at, usar ahora
        if data.get('status') == 'published' and not published_at:
            published_at = datetime.utcnow()
        
        post = BlogPost(
            author_id=author_id,
            title=data['title'],
            slug=slug,
            excerpt=data.get('excerpt'),
            content=data.get('content'),
            cover_image_url=data.get('cover_image_url'),
            meta_title=data.get('meta_title'),
            meta_description=data.get('meta_description'),
            status=data.get('status', 'draft'),
            published_at=published_at
        )
        
        db.session.add(post)
        db.session.flush()  # Para obtener el ID antes del commit
        
        # Crear keywords si se proporcionan
        keywords_list = data.get('keywords', [])
        for idx, keyword_data in enumerate(keywords_list):
            if isinstance(keyword_data, str):
                keyword = keyword_data
            else:
                keyword = keyword_data.get('keyword', '')
            
            if keyword:
                blog_keyword = BlogPostKeyword(
                    post_id=post.id,
                    keyword=keyword,
                    position=idx
                )
                db.session.add(blog_keyword)
        
        # Crear imágenes si se proporcionan
        images_list = data.get('images', [])
        for idx, image_data in enumerate(images_list):
            blog_image = BlogPostImage(
                post_id=post.id,
                image_url=image_data.get('image_url', ''),
                alt_text=image_data.get('alt_text'),
                position=image_data.get('position', idx)
            )
            db.session.add(blog_image)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': post.to_dict(include_keywords=True, include_images=True)
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

@blog_bp.route('/<uuid:post_id>', methods=['PUT'])
@admin_required
def update_blog_post(post_id):
    """Actualizar un post del blog"""
    try:
        post = BlogPost.query.get_or_404(post_id)
        data = request.get_json()
        
        if 'title' in data:
            post.title = data['title']
        
        # Actualizar slug si se proporciona o si cambió el título
        if 'slug' in data:
            new_slug = data['slug']
        elif 'title' in data:
            new_slug = generate_slug(data['title'])
        else:
            new_slug = post.slug
        
        # Verificar que el slug sea único (excepto para el mismo post)
        if new_slug != post.slug:
            existing_post = BlogPost.query.filter_by(slug=new_slug).first()
            if existing_post and existing_post.id != post.id:
                # Agregar número al slug si ya existe
                counter = 1
                while BlogPost.query.filter_by(slug=f"{new_slug}-{counter}").first():
                    counter += 1
                new_slug = f"{new_slug}-{counter}"
        
        post.slug = new_slug
        
        if 'excerpt' in data:
            post.excerpt = data.get('excerpt')
        if 'content' in data:
            post.content = data.get('content')
        if 'cover_image_url' in data:
            post.cover_image_url = data.get('cover_image_url')
        if 'meta_title' in data:
            post.meta_title = data.get('meta_title')
        if 'meta_description' in data:
            post.meta_description = data.get('meta_description')
        if 'status' in data:
            post.status = data.get('status')
            # Si se publica y no tiene published_at, establecerlo
            if data.get('status') == 'published' and not post.published_at:
                post.published_at = datetime.utcnow()
        
        if 'published_at' in data:
            if data['published_at']:
                try:
                    post.published_at = datetime.fromisoformat(data['published_at'].replace('Z', '+00:00'))
                except:
                    pass
            else:
                post.published_at = None
        
        post.updated_at = datetime.utcnow()
        
        # Actualizar keywords si se proporcionan
        if 'keywords' in data:
            # Eliminar keywords existentes
            BlogPostKeyword.query.filter_by(post_id=post.id).delete()
            
            # Crear nuevas keywords
            keywords_list = data['keywords']
            for idx, keyword_data in enumerate(keywords_list):
                if isinstance(keyword_data, str):
                    keyword = keyword_data
                else:
                    keyword = keyword_data.get('keyword', '')
                
                if keyword:
                    blog_keyword = BlogPostKeyword(
                        post_id=post.id,
                        keyword=keyword,
                        position=idx
                    )
                    db.session.add(blog_keyword)
        
        # Actualizar imágenes si se proporcionan
        if 'images' in data:
            # Eliminar imágenes existentes
            BlogPostImage.query.filter_by(post_id=post.id).delete()
            
            # Crear nuevas imágenes
            images_list = data['images']
            for idx, image_data in enumerate(images_list):
                blog_image = BlogPostImage(
                    post_id=post.id,
                    image_url=image_data.get('image_url', ''),
                    alt_text=image_data.get('alt_text'),
                    position=image_data.get('position', idx)
                )
                db.session.add(blog_image)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': post.to_dict(include_keywords=True, include_images=True)
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

@blog_bp.route('/<uuid:post_id>', methods=['DELETE'])
@admin_required
def delete_blog_post(post_id):
    """Eliminar un post del blog"""
    try:
        post = BlogPost.query.get_or_404(post_id)
        
        db.session.delete(post)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Post eliminado correctamente'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@blog_bp.route('/<uuid:post_id>/images', methods=['POST'])
@admin_required
def add_blog_post_image(post_id):
    """Agregar una imagen a un post"""
    try:
        post = BlogPost.query.get_or_404(post_id)
        data = request.get_json()
        
        if not data or not data.get('image_url'):
            return jsonify({
                'success': False,
                'error': 'image_url es requerido'
            }), 400
        
        # Obtener la posición máxima y agregar 1
        max_position = db.session.query(func.max(BlogPostImage.position)).filter_by(post_id=post_id).scalar() or -1
        
        blog_image = BlogPostImage(
            post_id=post_id,
            image_url=data['image_url'],
            alt_text=data.get('alt_text'),
            position=max_position + 1
        )
        
        db.session.add(blog_image)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': blog_image.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@blog_bp.route('/images/<uuid:image_id>', methods=['DELETE'])
@admin_required
def delete_blog_post_image(image_id):
    """Eliminar una imagen de un post"""
    try:
        image = BlogPostImage.query.get_or_404(image_id)
        
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

