from database import db
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid

class CrmDeliveryZone(db.Model):
    __tablename__ = 'crm_delivery_zones'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    crm_zone_id = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    notice_days = db.Column(db.Integer, nullable=True)
    public_html = db.Column(db.Text, nullable=True)
    private_html = db.Column(db.Text, nullable=True)
    surface_geojson = db.Column(JSONB, nullable=True)
    surface_raw = db.Column(db.Text, nullable=True)
    crm_created_at = db.Column(db.DateTime, nullable=True)
    crm_updated_at = db.Column(db.DateTime, nullable=True)
    crm_deleted_at = db.Column(db.DateTime, nullable=True)
    last_sync_action = db.Column(db.String(50), nullable=True)
    last_sync_at = db.Column(db.DateTime, nullable=True)
    raw = db.Column(JSONB, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relación con localidades
    zone_localities = db.relationship('CrmZoneLocality', backref='crm_zone', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': str(self.id),
            'crm_zone_id': self.crm_zone_id,
            'name': self.name,
            'notice_days': self.notice_days,
            'public_html': self.public_html,
            'private_html': self.private_html,
            'surface_geojson': self.surface_geojson,
            'surface_raw': self.surface_raw,
            'crm_created_at': self.crm_created_at.isoformat() if self.crm_created_at else None,
            'crm_updated_at': self.crm_updated_at.isoformat() if self.crm_updated_at else None,
            'crm_deleted_at': self.crm_deleted_at.isoformat() if self.crm_deleted_at else None,
            'last_sync_action': self.last_sync_action,
            'last_sync_at': self.last_sync_at.isoformat() if self.last_sync_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class CrmZoneLocality(db.Model):
    __tablename__ = 'crm_zone_localities'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    crm_zone_id = db.Column(db.Integer, db.ForeignKey('crm_delivery_zones.crm_zone_id'), nullable=False)
    locality_id = db.Column(UUID(as_uuid=True), db.ForeignKey('localities.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relación con Locality
    locality = db.relationship('Locality', backref='zone_associations', lazy=True)

    def to_dict(self):
        return {
            'id': str(self.id),
            'crm_zone_id': self.crm_zone_id,
            'locality_id': str(self.locality_id),
            'locality_name': self.locality.name if self.locality else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
