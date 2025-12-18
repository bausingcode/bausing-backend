from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name = db.Column(db.String(255), nullable=False)
    last_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    phone = db.Column(db.String(50), nullable=True)
    dni = db.Column(db.String(50), nullable=True)
    password_hash = db.Column(db.Text, nullable=False)
    email_verified = db.Column(db.Boolean, default=False, nullable=True)
    is_suspended = db.Column(db.Boolean, default=False, nullable=False)
    # Columnas de verificación de email (comentadas hasta que se agreguen a la BD)
    # email_verification_token = db.Column(db.String(255), nullable=True)
    # email_verification_token_expires = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        # Si email_verified no se proporciona, usar False por defecto
        if self.email_verified is None:
            self.email_verified = False

    # Relaciones (usando strings para evitar importaciones circulares)
    # Estas relaciones se activarán cuando se creen los modelos correspondientes
    # addresses = db.relationship('Address', backref='user', lazy=True, cascade='all, delete-orphan')
    # carts = db.relationship('Cart', backref='user', lazy=True)
    # orders = db.relationship('Order', backref='user', lazy=True)
    # wallet = db.relationship('Wallet', backref='user', uselist=False, lazy=True)

    def set_password(self, password):
        """Genera el hash de la contraseña"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verifica la contraseña"""
        return check_password_hash(self.password_hash, password)

    def to_dict(self, include_sensitive=False):
        """Convierte el usuario a diccionario"""
        data = {
            'id': str(self.id),
            'first_name': self.first_name,
            'last_name': self.last_name,
            'email': self.email,
            'phone': self.phone,
            'dni': self.dni,
            'email_verified': getattr(self, 'email_verified', False),
            'is_suspended': getattr(self, 'is_suspended', False),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        return data

