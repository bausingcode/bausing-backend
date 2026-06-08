import uuid
from datetime import datetime, timezone

from database import db
from sqlalchemy.dialects.postgresql import UUID


class Coupon(db.Model):
    __tablename__ = "coupons"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = db.Column(db.String(64), nullable=False, unique=True)
    discount_type = db.Column(
        db.String(20), nullable=False, default="percentage"
    )  # percentage | fixed
    discount_value = db.Column(db.Numeric(12, 2), nullable=False)
    max_uses = db.Column(db.Integer, nullable=True)
    uses_count = db.Column(db.Integer, nullable=False, default=0)
    valid_from = db.Column(db.DateTime(timezone=True), nullable=True)
    valid_until = db.Column(db.DateTime(timezone=True), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    club_beneficios_only = db.Column(db.Boolean, nullable=False, default=False)
    # null = aplica a todo el catálogo; UUID = solo al producto específico
    product_id = db.Column(UUID(as_uuid=True), nullable=True, default=None)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Descuentos específicos por categoría/subcategoría (solo aplica a club_beneficios_only + percentage)
    category_discounts = db.relationship(
        "CouponCategoryDiscount",
        cascade="all, delete-orphan",
        lazy="select",
        foreign_keys="[CouponCategoryDiscount.coupon_id]",
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "code": self.code,
            "discount_type": self.discount_type,
            "discount_value": float(self.discount_value)
            if self.discount_value is not None
            else 0.0,
            "max_uses": self.max_uses,
            "uses_count": int(self.uses_count or 0),
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "is_active": bool(self.is_active),
            "club_beneficios_only": bool(self.club_beneficios_only),
            "product_id": str(self.product_id) if self.product_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "category_discounts": [cd.to_dict() for cd in (self.category_discounts or [])],
        }
