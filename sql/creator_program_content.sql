CREATE TABLE IF NOT EXISTS creator_program_content (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  content JSON NOT NULL DEFAULT '{}',
  updated_by UUID REFERENCES admin_users(id),
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

INSERT INTO creator_program_content (content)
SELECT '{
  "hero_title": "Programa de Creadores",
  "hero_subtitle": "Creá contenido y ganá con Bausing",
  "hero_description": "Si te gusta hacer contenido, hablar a cámara o editar videos, este programa es para vos. En Bausing buscamos personas que quieran recomendar nuestros productos de forma auténtica y ayudar a otros a mejorar su descanso y bienestar.",
  "steps_title": "¿Qué tenés que hacer?",
  "steps": ["Crear contenido mostrando o recomendando productos Bausing", "Compartirlo en tus redes sociales", "Conectar con tu comunidad de forma real"],
  "requirements_title": "¿Qué necesitás para participar?",
  "requirements": ["Tener al menos una red social activa (Instagram, TikTok, X o YouTube)", "Perfil público", "Ganas de crear contenido"],
  "requirements_note": "No hace falta ser influencer. Buscamos autenticidad.",
  "join_title": "¿Cómo me sumo?",
  "join_description": "Es muy simple. Enviá un mensaje por WhatsApp:",
  "whatsapp_number": "5493518737683",
  "whatsapp_message": "Hola, quiero sumarme al Programa de Creadores de Bausing",
  "join_followup": "Vamos a revisar tu perfil y, si cumplís con los requisitos, te confirmamos el ingreso al programa. Una vez dentro, ya podés empezar a crear contenido y generar ingresos.",
  "benefits_title": "¿Por qué sumarte?",
  "benefits": ["Monetizás tu contenido", "Trabajás con una marca en crecimiento", "Ayudás a otras personas a mejorar su descanso"],
  "cta_title": "¿Listo para empezar?",
  "cta_button_text": "Quiero ser creador"
}'::json
WHERE NOT EXISTS (SELECT 1 FROM creator_program_content);
