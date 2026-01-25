from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    parent_id = db.Column(UUID(as_uuid=True), db.ForeignKey('categories.id'), nullable=True)
    order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    parent = db.relationship('Category', remote_side=[id], backref='children')
    products = db.relationship('Product', backref='category', lazy=True)
    options = db.relationship('CategoryOption', backref='category', lazy=True, cascade='all, delete-orphan', order_by='CategoryOption.position')

    def to_dict(self, include_options=False):
        data = {
            'id': str(self.id),
            'name': self.name,
            'description': self.description,
            'parent_id': str(self.parent_id) if self.parent_id else None,
            'parent_name': self.parent.name if self.parent else None,
            'order': self.order,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_options:
            data['options'] = [option.to_dict() for option in sorted(self.options, key=lambda x: x.position)]
        return data


class CategoryOption(db.Model):
    __tablename__ = 'category_options'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id = db.Column(UUID(as_uuid=True), db.ForeignKey('categories.id'), nullable=False)
    value = db.Column(db.String(255), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': str(self.id),
            'category_id': str(self.category_id),
            'value': self.value,
            'position': self.position,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

