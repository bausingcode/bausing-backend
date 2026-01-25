from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class Order(db.Model):
    """Modelo básico para la tabla orders (requerido para foreign keys)"""
    __tablename__ = 'orders'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    crm_order_id = db.Column(db.Integer, nullable=True)
    total = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    payment_method = db.Column(db.String(50), nullable=True)
    used_wallet_amount = db.Column(db.Numeric(10, 2), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relación con User
    user = db.relationship('User', backref='orders', lazy=True)

    def to_dict(self):
        """Convierte la orden a diccionario"""
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'total': float(self.total) if self.total else 0.0,
            'status': self.status,
            'payment_method': self.payment_method,
            'used_wallet_amount': float(self.used_wallet_amount) if self.used_wallet_amount else 0.0,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

