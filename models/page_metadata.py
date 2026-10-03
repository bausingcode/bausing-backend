from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid


class PageMetadata(db.Model):
    __tablename__ = "page_metadata"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    path = db.Column(db.Text, nullable=False, unique=True)
    # "category" | "institutional" — informativo, no se valida contra nada
    page_type = db.Column(db.Text, nullable=False)
    meta_title = db.Column(db.Text, nullable=True)
    meta_description = db.Column(db.Text, nullable=True)
    updated_by = db.Column(UUID(as_uuid=True), db.ForeignKey('admin_users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "path": self.path,
            "page_type": self.page_type,
            "meta_title": self.meta_title,
            "meta_description": self.meta_description,
            "updated_by": str(self.updated_by) if self.updated_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
