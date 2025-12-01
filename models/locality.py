from database import db
from sqlalchemy.dialects.postgresql import UUID
import uuid

class Locality(db.Model):
    __tablename__ = 'localities'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    region = db.Column(db.String(255))

    # Relaciones
    product_prices = db.relationship('ProductPrice', backref='locality', lazy=True)

    def to_dict(self):
        return {
            'id': str(self.id),
            'name': self.name,
            'region': self.region
        }

