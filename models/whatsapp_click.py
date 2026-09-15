from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class WhatsappClick(db.Model):
    __tablename__ = 'whatsapp_clicks'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # 'contact' = botón de contacto genérico por WhatsApp
    # 'checkout' = intento de finalizar la venta por WhatsApp (checkout)
    click_type = db.Column(db.String(20), nullable=False)
    page = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': str(self.id),
            'click_type': self.click_type,
            'page': self.page,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
