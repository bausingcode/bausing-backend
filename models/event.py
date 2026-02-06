from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class Event(db.Model):
    __tablename__ = 'events'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    text = db.Column(db.String(500), nullable=False)  # Texto a mostrar en la barra
    background_color = db.Column(db.String(7), nullable=False, default='#111827')  # Color de fondo (hex)
    text_color = db.Column(db.String(7), nullable=False, default='#FFFFFF')  # Color de texto (hex)
    is_active = db.Column(db.Boolean, default=False, nullable=False)  # Si el evento está activo
    display_type = db.Column(db.String(20), nullable=False, default='fixed')  # 'fixed' o 'countdown'
    countdown_end_date = db.Column(db.DateTime, nullable=True)  # Fecha de fin para countdown (opcional)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Convierte el evento a diccionario"""
        return {
            'id': str(self.id),
            'text': self.text,
            'background_color': self.background_color,
            'text_color': self.text_color,
            'is_active': self.is_active,
            'display_type': self.display_type,
            'countdown_end_date': self.countdown_end_date.isoformat() if self.countdown_end_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
