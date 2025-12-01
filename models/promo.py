from database import db
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid

class Promo(db.Model):
    __tablename__ = 'promos'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    type = db.Column(db.String(50), nullable=False)  # percentage, fixed, 2x1, bundle, wallet_multiplier
    value = db.Column(db.Numeric(10, 2), nullable=False)
    extra_config = db.Column(JSONB, nullable=True)  # ej: {"buy":2,"pay":1}
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    applicability = db.relationship('PromoApplicability', backref='promo', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, include_applicability=False):
        data = {
            'id': str(self.id),
            'title': self.title,
            'description': self.description,
            'type': self.type,
            'value': float(self.value),
            'extra_config': self.extra_config or {},
            'start_at': self.start_at.isoformat() if self.start_at else None,
            'end_at': self.end_at.isoformat() if self.end_at else None,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_applicability:
            data['applicability'] = [app.to_dict() for app in self.applicability]
        return data

    def is_valid(self):
        """Verifica si la promoción está vigente"""
        now = datetime.utcnow()
        return (
            self.is_active and
            self.start_at <= now <= self.end_at
        )


class PromoApplicability(db.Model):
    __tablename__ = 'promo_applicability'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    promo_id = db.Column(UUID(as_uuid=True), db.ForeignKey('promos.id'), nullable=False)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=True)
    category_id = db.Column(UUID(as_uuid=True), db.ForeignKey('categories.id'), nullable=True)
    variant_id = db.Column(UUID(as_uuid=True), db.ForeignKey('product_variants.id'), nullable=True)
    applies_to = db.Column(db.String(50), nullable=False)  # "product", "category", "variant", "all"

    # Relaciones
    product = db.relationship('Product', backref='promo_applicabilities', lazy=True)
    category = db.relationship('Category', backref='promo_applicabilities', lazy=True)
    variant = db.relationship('ProductVariant', backref='promo_applicabilities', lazy=True)

    def to_dict(self):
        data = {
            'id': str(self.id),
            'promo_id': str(self.promo_id),
            'applies_to': self.applies_to
        }
        
        if self.product_id:
            data['product_id'] = str(self.product_id)
            data['product_name'] = self.product.name if self.product else None
        
        if self.category_id:
            data['category_id'] = str(self.category_id)
            data['category_name'] = self.category.name if self.category else None
        
        if self.variant_id:
            data['variant_id'] = str(self.variant_id)
            data['variant_name'] = self.variant.variant_name if self.variant else None
        
        return data

