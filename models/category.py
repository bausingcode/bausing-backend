from database import db
from sqlalchemy.dialects.postgresql import UUID
import uuid

class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    parent_id = db.Column(UUID(as_uuid=True), db.ForeignKey('categories.id'), nullable=True)

    # Relaciones
    parent = db.relationship('Category', remote_side=[id], backref='children')
    products = db.relationship('Product', backref='category', lazy=True)

    def to_dict(self):
        return {
            'id': str(self.id),
            'name': self.name,
            'description': self.description,
            'parent_id': str(self.parent_id) if self.parent_id else None,
            'parent_name': self.parent.name if self.parent else None
        }

