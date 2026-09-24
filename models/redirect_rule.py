from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid


class RedirectRule(db.Model):
    __tablename__ = "redirect_rules"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_path = db.Column(db.Text, nullable=False, unique=True)
    target_path = db.Column(db.Text, nullable=False)
    redirect_type = db.Column(db.Integer, nullable=False, default=301)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    hit_count = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "source_path": self.source_path,
            "target_path": self.target_path,
            "redirect_type": self.redirect_type,
            "is_active": self.is_active,
            "hit_count": self.hit_count,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
