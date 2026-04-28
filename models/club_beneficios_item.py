from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid


class ClubBeneficiosItem(db.Model):
    __tablename__ = 'club_beneficios_items'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    position = db.Column(db.Integer, nullable=False, unique=True)
    product_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('products.id'),
        nullable=False,
        unique=True,
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    product = db.relationship('Product', backref='club_beneficios_items', lazy=True)

    def to_dict(self, include_product=False, product_price_map=None, product_promos_map=None):
        data = {
            'id': str(self.id),
            'position': int(self.position) if self.position is not None else 0,
            'product_id': str(self.product_id) if self.product_id else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
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
                        prod.id,
                        {'min': 0.0, 'max': 0.0},
                    )
                    precalc_min = pair.get('min')
                    precalc_max = pair.get('max')

                promos_kw = {}
                if product_promos_map is not None:
                    promos_kw['precalculated_promos'] = product_promos_map.get(prod.id, [])

                data['product'] = prod.to_dict(
                    include_variants=False,
                    include_images=True,
                    include_promos=True,
                    include_inventory=False,
                    precalculated_min_price=precalc_min,
                    precalculated_max_price=precalc_max,
                    **promos_kw,
                )

        return data
