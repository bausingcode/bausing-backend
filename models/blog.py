from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class BlogPost(db.Model):
    __tablename__ = 'blog_posts'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_id = db.Column(UUID(as_uuid=True), db.ForeignKey('admin_users.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), nullable=False, unique=True)
    excerpt = db.Column(db.Text)
    content = db.Column(db.Text)
    cover_image_url = db.Column(db.Text)
    meta_title = db.Column(db.String(255))
    meta_description = db.Column(db.Text)
    status = db.Column(db.String(50), default='draft', nullable=False)  # draft, published
    published_at = db.Column(db.DateTime)
    view_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relaciones
    author = db.relationship('AdminUser', backref='blog_posts', lazy=True)
    keywords = db.relationship('BlogPostKeyword', backref='post', lazy=True, cascade='all, delete-orphan', order_by='BlogPostKeyword.position')
    images = db.relationship('BlogPostImage', backref='post', lazy=True, cascade='all, delete-orphan', order_by='BlogPostImage.position')

    def to_dict(self, include_keywords=True, include_images=True):
        data = {
            'id': str(self.id),
            'author_id': str(self.author_id),
            'title': self.title,
            'slug': self.slug,
            'excerpt': self.excerpt,
            'content': self.content,
            'cover_image_url': self.cover_image_url,
            'meta_title': self.meta_title,
            'meta_description': self.meta_description,
            'status': self.status,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'view_count': self.view_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_keywords:
            data['keywords'] = [kw.to_dict() for kw in self.keywords]
        
        if include_images:
            data['images'] = [img.to_dict() for img in self.images]
        
        if self.author:
            data['author'] = {
                'id': str(self.author.id),
                'email': self.author.email
            }
        
        return data


class BlogPostKeyword(db.Model):
    __tablename__ = 'blog_post_keywords'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id = db.Column(UUID(as_uuid=True), db.ForeignKey('blog_posts.id'), nullable=False)
    keyword = db.Column(db.String(255), nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': str(self.id),
            'post_id': str(self.post_id),
            'keyword': self.keyword,
            'position': self.position,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class BlogPostImage(db.Model):
    __tablename__ = 'blog_post_images'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id = db.Column(UUID(as_uuid=True), db.ForeignKey('blog_posts.id'), nullable=False)
    image_url = db.Column(db.Text, nullable=False)
    alt_text = db.Column(db.String(255))
    position = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': str(self.id),
            'post_id': str(self.post_id),
            'image_url': self.image_url,
            'alt_text': self.alt_text,
            'position': self.position,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

