from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class Cart(db.Model):
    __tablename__ = 'carts'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relación con User
    user = db.relationship('User', backref='carts', lazy=True)

    def to_dict(self):
        """Convierte el carrito a diccionario"""
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
