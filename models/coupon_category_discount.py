import uuid
from database import db
from sqlalchemy.dialects.postgresql import UUID


class CouponCategoryDiscount(db.Model):
    __tablename__ = "coupon_category_discounts"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coupon_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("coupons.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Categoría principal. Si solo se especifica esto, aplica a toda la categoría.
    category_id = db.Column(UUID(as_uuid=True), nullable=True)
    # Subcategoría específica. Toma precedencia sobre category_id.
    subcategory_id = db.Column(UUID(as_uuid=True), nullable=True)
    # Porcentaje de descuento (ej: 10.0 = 10%)
    discount_value = db.Column(db.Numeric(12, 2), nullable=False)

    def to_dict(self):
        return {
            "id": str(self.id),
            "coupon_id": str(self.coupon_id),
            "category_id": str(self.category_id) if self.category_id else None,
            "subcategory_id": str(self.subcategory_id) if self.subcategory_id else None,
            "discount_value": float(self.discount_value),
        }
