from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import db
from datetime import datetime
import uuid

class CardType(db.Model):
    __tablename__ = 'card_types'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = db.Column(db.String(50), unique=True, nullable=False)  # visa, mastercard, amex
    name = db.Column(db.String(100), nullable=False)  # Visa, Mastercard, American Express
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relación con installments
    installments = relationship('CardBankInstallment', back_populates='card_type', cascade='all, delete-orphan')

    def to_dict(self, include_installments=False):
        data = {
            'id': str(self.id),
            'code': self.code,
            'name': self.name,
            'is_active': self.is_active,
            'display_order': self.display_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_installments:
            data['installments'] = [inst.to_dict() for inst in self.installments if inst.is_active]
        
        return data
