from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import db
from datetime import datetime
import uuid

class CardBankInstallment(db.Model):
    __tablename__ = 'card_bank_installments'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_type_id = db.Column(UUID(as_uuid=True), ForeignKey('card_types.id', ondelete='CASCADE'), nullable=False)
    bank_id = db.Column(UUID(as_uuid=True), ForeignKey('banks.id', ondelete='CASCADE'), nullable=False)
    installments = db.Column(db.Integer, nullable=False)  # número de cuotas (1, 3, 6, 12, etc.)
    surcharge_percentage = db.Column(db.Numeric(5, 2), nullable=False, default=0)  # porcentaje de recargo
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relaciones
    card_type = relationship('CardType', back_populates='installments')
    bank = relationship('Bank', back_populates='installments')

    # Constraint único para evitar duplicados
    __table_args__ = (
        UniqueConstraint('card_type_id', 'bank_id', 'installments', name='unique_card_bank_installments'),
    )

    def to_dict(self, include_card_type=False, include_bank=False):
        data = {
            'id': str(self.id),
            'card_type_id': str(self.card_type_id),
            'bank_id': str(self.bank_id),
            'installments': self.installments,
            'surcharge_percentage': float(self.surcharge_percentage),
            'is_active': self.is_active,
            'display_order': self.display_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_card_type and self.card_type:
            data['card_type'] = self.card_type.to_dict()
        
        if include_bank and self.bank:
            data['bank'] = self.bank.to_dict()
        
        return data
