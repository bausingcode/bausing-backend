"""Sugerencias 'Completa tu compra' en PDP: hasta 2 productos por categoría principal."""
from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid


class CategoryPdpCrossSell(db.Model):
    __tablename__ = 'category_pdp_cross_sell'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('categories.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
    )
    product_id_1 = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('products.id', ondelete='SET NULL'),
        nullable=True,
    )
    product_id_2 = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('products.id', ondelete='SET NULL'),
        nullable=True,
    )
    product_id_3 = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('products.id', ondelete='SET NULL'),
        nullable=True,
    )
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('admin_users.id', ondelete='SET NULL'),
        nullable=True,
    )

    def ordered_product_ids(self):
        out = []
        for pid in (self.product_id_1, self.product_id_2):
            if pid is not None:
                out.append(str(pid))
        return out
