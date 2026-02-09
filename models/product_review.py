from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone, timedelta
import uuid

def get_argentina_time():
    """Retorna la fecha y hora actual en zona horaria de Argentina (UTC-3) como datetime naive"""
    argentina_tz = timezone(timedelta(hours=-3))
    return datetime.now(argentina_tz).replace(tzinfo=None)

class ProductReview(db.Model):
    """Modelo para las reseñas de productos"""
    __tablename__ = 'product_reviews'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # ownership
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey('orders.id'), nullable=False)
    order_item_id = db.Column(UUID(as_uuid=True), db.ForeignKey('order_items.id'), nullable=False)
    
    # product link
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=False)
    product_variant_id = db.Column(UUID(as_uuid=True), db.ForeignKey('product_variants.id'), nullable=True)  # opcional
    
    # content
    rating = db.Column(db.Integer, nullable=False)  # 1..5
    title = db.Column(db.String(255), nullable=True)
    comment = db.Column(db.Text, nullable=True)
    
    # moderation / state
    status = db.Column(db.String(50), nullable=False, default='published')  # published | hidden | pending | deleted
    is_verified_purchase = db.Column(db.Boolean, nullable=False, default=True)
    
    # timestamps
    created_at = db.Column(db.DateTime, default=lambda: get_argentina_time(), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: get_argentina_time(), onupdate=lambda: get_argentina_time(), nullable=False)
    
    # Relaciones
    user = db.relationship('User', backref='product_reviews', lazy=True)
    order = db.relationship('Order', backref='product_reviews', lazy=True)
    order_item = db.relationship('OrderItem', backref='product_reviews', lazy=True)
    product = db.relationship('Product', backref='product_reviews', lazy=True)
    product_variant = db.relationship('ProductVariant', backref='product_reviews', lazy=True)
    
    def to_dict(self):
        """Convierte la reseña a diccionario"""
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'order_id': str(self.order_id),
            'order_item_id': str(self.order_item_id),
            'product_id': str(self.product_id),
            'product_variant_id': str(self.product_variant_id) if self.product_variant_id else None,
            'rating': self.rating,
            'title': self.title,
            'comment': self.comment,
            'status': self.status,
            'is_verified_purchase': self.is_verified_purchase,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'user_name': f"{self.user.first_name} {self.user.last_name}" if self.user else None
        }
