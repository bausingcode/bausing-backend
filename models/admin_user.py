from database import db
from sqlalchemy.dialects.postgresql import UUID
import uuid
from werkzeug.security import generate_password_hash, check_password_hash

class AdminRole(db.Model):
    __tablename__ = 'admin_roles'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(100), nullable=False, unique=True)

    # Relaciones
    admin_users = db.relationship('AdminUser', backref='role', lazy=True)

    def to_dict(self):
        return {
            'id': str(self.id),
            'name': self.name
        }


class AdminUser(db.Model):
    __tablename__ = 'admin_users'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.Text, nullable=False)
    role_id = db.Column(UUID(as_uuid=True), db.ForeignKey('admin_roles.id'), nullable=False)

    def set_password(self, password):
        """Genera el hash de la contraseña"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verifica la contraseña"""
        return check_password_hash(self.password_hash, password)

    def to_dict(self, include_role=True):
        data = {
            'id': str(self.id),
            'email': self.email,
            'role_id': str(self.role_id)
        }
        if include_role and self.role:
            data['role'] = self.role.to_dict()
        return data


