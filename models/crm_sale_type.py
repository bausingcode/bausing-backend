from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class CrmSaleType(db.Model):
    __tablename__ = 'crm_sale_types'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    crm_sale_type_id = db.Column(db.Integer, unique=True, nullable=False)
    code = db.Column(db.String(255), nullable=True)
    description = db.Column(db.String(255), nullable=True)
    number = db.Column(db.Integer, nullable=True)
    vat_condition_receiver_id = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    sale_type_id = db.Column(UUID(as_uuid=True), nullable=True)
    raw = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Convierte el tipo de venta a diccionario"""
        return {
            'id': str(self.id),
            'crm_sale_type_id': self.crm_sale_type_id,
            'code': self.code,
            'description': self.description,
            'number': self.number,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
