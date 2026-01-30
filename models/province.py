from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class Province(db.Model):
    __tablename__ = 'provinces'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), nullable=True)  # opcional, ej "AR-X"
    country_code = db.Column(db.String(10), nullable=True)  # opcional, ej "AR"
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Convierte la provincia a diccionario"""
        return {
            'id': str(self.id),
            'name': self.name,
            'code': self.code,
            'country_code': self.country_code,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
