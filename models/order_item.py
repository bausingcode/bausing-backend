from database import db
from sqlalchemy.dialects.postgresql import UUID
# from datetime import datetime  # Comentado porque created_at no existe en la tabla
import uuid

class OrderItem(db.Model):
    """Modelo para los items de una orden"""
    __tablename__ = 'order_items'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=False)
    # variant_id comentado temporalmente porque la columna no existe en la tabla order_items
    # Si necesitas variant_id, necesitas hacer una migración para agregar la columna
    # variant_id = db.Column(UUID(as_uuid=True), db.ForeignKey('product_variants.id'), nullable=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)  # La columna en la BD es unit_price, no price
    # created_at comentado porque la columna no existe en la tabla order_items
    # created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    order = db.relationship('Order', backref='order_items', lazy=True)
    product = db.relationship('Product', backref='order_items', lazy=True)
    # variant = db.relationship('ProductVariant', backref='order_items', lazy=True)

    def to_dict(self):
        """Convierte el item de orden a diccionario"""
        return {
            'id': str(self.id),
            'order_id': str(self.order_id),
            'product_id': str(self.product_id),
            # 'variant_id': str(self.variant_id) if self.variant_id else None,  # Comentado porque la columna no existe
            'quantity': self.quantity,
            'price': float(self.unit_price) if self.unit_price else 0.0,  # unit_price es el precio unitario
            'unit_price': float(self.unit_price) if self.unit_price else 0.0
            # 'created_at': self.created_at.isoformat() if self.created_at else None  # Comentado porque la columna no existe
        }
