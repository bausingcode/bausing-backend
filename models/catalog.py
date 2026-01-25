from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class Catalog(db.Model):
    __tablename__ = 'catalogs'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relaciones
    locality_associations = db.relationship('LocalityCatalog', backref='catalog', lazy=True, cascade='all, delete-orphan')
    product_prices = db.relationship('ProductPrice', backref='catalog', lazy=True)

    def to_dict(self, include_localities=False):
        data = {
            'id': str(self.id),
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_localities:
            data['localities'] = [
                {
                    'id': str(assoc.locality.id),
                    'name': assoc.locality.name,
                    'region': assoc.locality.region
                }
                for assoc in self.locality_associations
            ]
        
        return data


class LocalityCatalog(db.Model):
    __tablename__ = 'locality_catalogs'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    locality_id = db.Column(UUID(as_uuid=True), db.ForeignKey('localities.id', ondelete='CASCADE'), nullable=False)
    catalog_id = db.Column(UUID(as_uuid=True), db.ForeignKey('catalogs.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relación con Locality
    locality = db.relationship('Locality', backref='catalog_associations', lazy=True)

    # Constraint único para evitar duplicados
    __table_args__ = (
        db.UniqueConstraint('locality_id', 'catalog_id', name='unique_locality_catalog'),
    )

    def to_dict(self):
        return {
            'id': str(self.id),
            'locality_id': str(self.locality_id),
            'catalog_id': str(self.catalog_id),
            'locality_name': self.locality.name if self.locality else None,
            'catalog_name': self.catalog.name if self.catalog else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
