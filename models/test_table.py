from database import db
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

class TestTable(db.Model):
    """
    Tabla de prueba para almacenar datos de sincronización.
    """
    __tablename__ = 'test_table'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    body = db.Column(JSONB, nullable=False)  # Almacena toda la información recibida
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Convierte el registro a diccionario"""
        return {
            'id': self.id,
            'body': self.body,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

