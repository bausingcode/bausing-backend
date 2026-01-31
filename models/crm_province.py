from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class CrmProvince(db.Model):
    __tablename__ = 'crm_provinces'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    crm_province_id = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, nullable=True)
    crm_created_at = db.Column(db.DateTime, nullable=True)
    crm_updated_at = db.Column(db.DateTime, nullable=True)
    last_sync_action = db.Column(db.String(50), nullable=True)
    last_sync_at = db.Column(db.DateTime, nullable=True)
    raw = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Convierte la provincia del CRM a diccionario"""
        return {
            'id': str(self.id),
            'crm_province_id': self.crm_province_id,
            'name': self.name,
            'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class CrmProvinceMap(db.Model):
    __tablename__ = 'crm_province_map'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    crm_province_id = db.Column(db.Integer, nullable=False)  # referencia a crm_provinces.crm_province_id
    province_id = db.Column(UUID(as_uuid=True), db.ForeignKey('provinces.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    province = db.relationship('Province', backref='crm_mappings', lazy=True)

    def to_dict(self):
        """Convierte el mapeo a diccionario"""
        return {
            'id': str(self.id),
            'crm_province_id': self.crm_province_id,
            'province_id': str(self.province_id),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
