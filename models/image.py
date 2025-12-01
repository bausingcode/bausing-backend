from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class ProductImage(db.Model):
    __tablename__ = 'product_images'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=False)
    image_url = db.Column(db.Text, nullable=False)
    alt_text = db.Column(db.String(255))
    position = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    product = db.relationship('Product', backref='images', lazy=True)

    def to_dict(self):
        return {
            'id': str(self.id),
            'product_id': str(self.product_id),
            'image_url': self.image_url,
            'alt_text': self.alt_text,
            'position': self.position,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class HeroImage(db.Model):
    __tablename__ = 'hero_images'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    image_url = db.Column(db.Text, nullable=False)
    title = db.Column(db.String(255))
    subtitle = db.Column(db.String(255))
    cta_text = db.Column(db.String(255))
    cta_link = db.Column(db.String(500))
    position = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': str(self.id),
            'image_url': self.image_url,
            'title': self.title,
            'subtitle': self.subtitle,
            'cta_text': self.cta_text,
            'cta_link': self.cta_link,
            'position': self.position,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


