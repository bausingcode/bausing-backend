from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class HomepageProductDistribution(db.Model):
    __tablename__ = 'homepage_product_distribution'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section = db.Column(db.String(50), nullable=False)  # 'featured', 'discounts', 'mattresses', 'complete_purchase'
    position = db.Column(db.Integer, nullable=False)  # 0-3 para featured, 0-2 para discounts, 0-3 para los otros
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=True)
    # False = publicado (sitio); True = borrador hasta publicar
    is_draft = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text('false'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('section', 'position', 'is_draft', name='uq_homepage_distribution_slot'),
    )

    # Relaciones
    product = db.relationship('Product', backref='homepage_distributions', lazy=True)

    def to_dict(self, include_product=False, product_price_map=None):
        data = {
            'id': str(self.id),
            'section': self.section,
            'position': self.position,
            'product_id': str(self.product_id) if self.product_id else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
        
        if include_product and self.product_id:
            prod = self.product
            if prod is None:
                from models.product import Product as ProductModel
                prod = db.session.get(ProductModel, self.product_id)
            if prod is not None:
                precalc_min = precalc_max = None
                if product_price_map is not None:
                    pair = product_price_map.get(
                        prod.id, {'min': 0.0, 'max': 0.0}
                    )
                    precalc_min = pair['min']
                    precalc_max = pair['max']
                data['product'] = prod.to_dict(
                    include_variants=False,
                    include_images=True,
                    include_promos=False,
                    include_inventory=False,
                    precalculated_min_price=precalc_min,
                    precalculated_max_price=precalc_max,
                )
        
        return data
