from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class DocType(db.Model):
    __tablename__ = 'doc_types'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = db.Column(db.String(255), nullable=False, unique=True)  # ej: DNI, CUIT, CUIL
    name = db.Column(db.String(255), nullable=False)
    crm_doc_type_id = db.Column(UUID(as_uuid=True), nullable=True)  # mapeo al CRM
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Convierte el tipo de documento a diccionario"""
        return {
            'id': str(self.id),
            'code': self.code,
            'name': self.name,
            'crm_doc_type_id': str(self.crm_doc_type_id) if self.crm_doc_type_id else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
