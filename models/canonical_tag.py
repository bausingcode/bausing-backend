from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid


class CanonicalTag(db.Model):
    __tablename__ = "canonical_tags"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    path = db.Column(db.Text, nullable=False, unique=True)
    canonical_url = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "path": self.path,
            "canonical_url": self.canonical_url,
            "is_active": self.is_active,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
