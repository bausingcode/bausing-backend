from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid


class CategoryFaqItem(db.Model):
    __tablename__ = "category_faq_items"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_published = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    category = db.relationship("Category")

    def to_dict(self):
        return {
            "id": str(self.id),
            "category_id": str(self.category_id),
            "category_name": self.category.name if self.category else None,
            "question": self.question,
            "answer": self.answer,
            "sort_order": self.sort_order,
            "is_published": self.is_published,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
