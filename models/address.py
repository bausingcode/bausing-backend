from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class Address(db.Model):
    __tablename__ = 'addresses'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(50), nullable=False)
    street = db.Column(db.String(255), nullable=False)
    number = db.Column(db.String(50), nullable=False)
    additional_info = db.Column(db.Text, nullable=True)
    postal_code = db.Column(db.String(20), nullable=False)
    city = db.Column(db.String(255), nullable=False)
    province = db.Column(db.String(255), nullable=False)
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relación con User
    user = db.relationship('User', backref='addresses')

    def to_dict(self):
        """Convierte la dirección a diccionario"""
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'full_name': self.full_name,
            'phone': self.phone,
            'street': self.street,
            'number': self.number,
            'additional_info': self.additional_info,
            'postal_code': self.postal_code,
            'city': self.city,
            'province': self.province,
            'is_default': self.is_default,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

