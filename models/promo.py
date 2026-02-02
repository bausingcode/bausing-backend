from database import db
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid

class Promo(db.Model):
    __tablename__ = 'promos'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    type = db.Column(db.String(50), nullable=False)  # percentage, fixed, 2x1, bundle, wallet_multiplier, promotional_message
    value = db.Column(db.Numeric(10, 2), nullable=True)  # Nullable para promotional_message
    extra_config = db.Column(JSONB, nullable=True)  # ej: {"buy":2,"pay":1,"custom_message":"OFERTA"}
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    allows_wallet = db.Column(db.Boolean, default=True, nullable=False)  # Compatible con Pesos Bausing
    # created_at puede no existir en la tabla - comentar hasta agregar la columna en DB
    # created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    applicability = db.relationship('PromoApplicability', backref='promo', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, include_applicability=False):
        data = {
            'id': str(self.id),
            'title': self.title,
            'description': self.description,
            'type': self.type,
            'value': float(self.value) if self.value is not None else 0,
            'extra_config': self.extra_config or {},
            'start_at': self.start_at.isoformat() if self.start_at else None,
            'end_at': self.end_at.isoformat() if self.end_at else None,
            'is_active': self.is_active,
            'allows_wallet': self.allows_wallet
        }
        # created_at puede no existir si la columna no está en la DB
        if hasattr(self, 'created_at') and self.created_at:
            data['created_at'] = self.created_at.isoformat()
        
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
    # product_variant_id = db.Column(UUID(as_uuid=True), db.ForeignKey('product_variants.id'), nullable=True)  # Column doesn't exist in DB
    applies_to = db.Column(db.String(50), nullable=False)  # "product", "category", "variant", "all"

    # Relaciones
    product = db.relationship('Product', backref='promo_applicabilities', lazy=True)
    category = db.relationship('Category', backref='promo_applicabilities', lazy=True)
    # variant = db.relationship('ProductVariant', backref='promo_applicabilities', lazy=True)  # Column doesn't exist

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
        
        # if self.product_variant_id:
        #     data['product_variant_id'] = str(self.product_variant_id)
        #     data['variant_name'] = self.variant.get_display_name() if self.variant else None
        
        return data

