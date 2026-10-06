from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

DEFAULT_CREATOR_PROGRAM_CONTENT = {
    "hero_title": "Programa de Creadores",
    "hero_subtitle": "Creá contenido y ganá con Bausing",
    "hero_description": (
        "Si te gusta hacer contenido, hablar a cámara o editar videos, este programa es "
        "para vos. En Bausing buscamos personas que quieran recomendar nuestros productos "
        "de forma auténtica y ayudar a otros a mejorar su descanso y bienestar."
    ),
    "steps_title": "¿Qué tenés que hacer?",
    "steps": [
        "Crear contenido mostrando o recomendando productos Bausing",
        "Compartirlo en tus redes sociales",
        "Conectar con tu comunidad de forma real",
    ],
    "requirements_title": "¿Qué necesitás para participar?",
    "requirements": [
        "Tener al menos una red social activa (Instagram, TikTok, X o YouTube)",
        "Perfil público",
        "Ganas de crear contenido",
    ],
    "requirements_note": "No hace falta ser influencer. Buscamos autenticidad.",
    "join_title": "¿Cómo me sumo?",
    "join_description": "Es muy simple. Enviá un mensaje por WhatsApp:",
    "whatsapp_number": "5493518737683",
    "whatsapp_message": "Hola, quiero sumarme al Programa de Creadores de Bausing",
    "join_followup": (
        "Vamos a revisar tu perfil y, si cumplís con los requisitos, te confirmamos el "
        "ingreso al programa. Una vez dentro, ya podés empezar a crear contenido y "
        "generar ingresos."
    ),
    "benefits_title": "¿Por qué sumarte?",
    "benefits": [
        "Monetizás tu contenido",
        "Trabajás con una marca en crecimiento",
        "Ayudás a otras personas a mejorar su descanso",
    ],
    "cta_title": "¿Listo para empezar?",
    "cta_button_text": "Quiero ser creador",
}


class CreatorProgramContent(db.Model):
    __tablename__ = "creator_program_content"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = db.Column(db.JSON, nullable=False, default=dict)
    updated_by = db.Column(UUID(as_uuid=True), db.ForeignKey("admin_users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def to_dict(self):
        merged = dict(DEFAULT_CREATOR_PROGRAM_CONTENT)
        merged.update(self.content or {})
        return merged

    @staticmethod
    def get_singleton():
        row = CreatorProgramContent.query.order_by(CreatorProgramContent.created_at.asc()).first()
        if not row:
            row = CreatorProgramContent(content=dict(DEFAULT_CREATOR_PROGRAM_CONTENT))
            db.session.add(row)
            db.session.commit()
        return row
