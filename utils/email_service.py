"""
Servicio de envío de emails usando Resend API
"""
from config import Config
import resend
from typing import Optional, Dict, Any
import os

class EmailService:
    """Servicio centralizado para el envío de emails"""
    
    def __init__(self):
        self.api_key_configured = False
        if Config.RESEND_API_KEY:
            resend.api_key = Config.RESEND_API_KEY
            self.api_key_configured = True
        self.from_email = Config.RESEND_FROM_EMAIL
    
    def _send_email(
        self,
        to: str | list[str],
        subject: str,
        html: str,
        from_email: Optional[str] = None
    ) -> bool:
        """
        Método interno para enviar emails.
        
        Args:
            to: Email o lista de emails destinatarios
            subject: Asunto del email
            html: Contenido HTML del email
            from_email: Email remitente (opcional, usa el configurado por defecto)
        
        Returns:
            True si se envió correctamente, False en caso contrario
        """
        try:
            if not self.api_key_configured:
                print("⚠️  RESEND_API_KEY no configurada. Email no enviado (modo desarrollo).")
                print(f"📧 Email que se habría enviado:")
                print(f"   Para: {to}")
                print(f"   Asunto: {subject}")
                return False
            
            # Asegurar que 'to' sea una lista
            if isinstance(to, str):
                to = [to]
            
            params = {
                "from": from_email or self.from_email,
                "to": to,
                "subject": subject,
                "html": html,
            }
            
            email = resend.Emails.send(params)
            
            print(f"✅ Email enviado correctamente a {', '.join(to)}")
            return True
            
        except Exception as e:
            print(f"❌ Error al enviar email: {str(e)}")
            return False
    
    def send_verification_email(self, user_email: str, user_first_name: str, verification_url: str) -> bool:
        """
        Envía email de verificación de cuenta.
        
        Args:
            user_email: Email del usuario
            user_first_name: Nombre del usuario
            verification_url: URL de verificación
        
        Returns:
            True si se envió correctamente
        """
        from .email_templates import get_email_verification_template
        
        html = get_email_verification_template(user_first_name, verification_url)
        return self._send_email(
            to=user_email,
            subject="Verifica tu email - Bausing",
            html=html
        )
    
    def send_password_reset_email(
        self,
        user_email: str,
        user_first_name: str,
        reset_url: str,
        expires_in: str = "1 hora"
    ) -> bool:
        """
        Envía email de recuperación de contraseña.
        
        Args:
            user_email: Email del usuario
            user_first_name: Nombre del usuario
            reset_url: URL para resetear la contraseña
            expires_in: Tiempo de expiración del enlace
        
        Returns:
            True si se envió correctamente
        """
        from .email_templates import get_password_reset_template
        
        html = get_password_reset_template(user_first_name, reset_url, expires_in)
        return self._send_email(
            to=user_email,
            subject="Restablecer contraseña - Bausing",
            html=html
        )
    
    def send_order_confirmation_email(
        self,
        user_email: str,
        user_first_name: str,
        order_number: str,
        order_total: str,
        order_url: Optional[str] = None
    ) -> bool:
        """
        Envía email de confirmación de pedido.
        
        Args:
            user_email: Email del usuario
            user_first_name: Nombre del usuario
            order_number: Número de pedido
            order_total: Total del pedido
            order_url: URL para ver el pedido (opcional)
        
        Returns:
            True si se envió correctamente
        """
        from .email_templates import get_order_confirmation_template
        
        html = get_order_confirmation_template(user_first_name, order_number, order_total, order_url)
        return self._send_email(
            to=user_email,
            subject=f"Confirmación de pedido #{order_number} - Bausing",
            html=html
        )
    
    def send_welcome_email(
        self,
        user_email: str,
        user_first_name: str,
        dashboard_url: Optional[str] = None
    ) -> bool:
        """
        Envía email de bienvenida.
        
        Args:
            user_email: Email del usuario
            user_first_name: Nombre del usuario
            dashboard_url: URL del dashboard (opcional)
        
        Returns:
            True si se envió correctamente
        """
        from .email_templates import get_welcome_template
        
        html = get_welcome_template(user_first_name, dashboard_url)
        return self._send_email(
            to=user_email,
            subject="¡Bienvenido a Bausing!",
            html=html
        )
    
    def send_custom_email(
        self,
        to: str | list[str],
        title: str,
        header_text: str,
        greeting: str,
        main_content: str,
        button_text: Optional[str] = None,
        button_url: Optional[str] = None,
        footer_note: Optional[str] = None
    ) -> bool:
        """
        Envía un email personalizado usando la plantilla genérica.
        
        Args:
            to: Email o lista de emails destinatarios
            title: Título del email
            header_text: Texto del header
            greeting: Saludo personalizado
            main_content: Contenido principal del email
            button_text: Texto del botón CTA (opcional)
            button_url: URL del botón CTA (opcional)
            footer_note: Nota adicional para el footer (opcional)
        
        Returns:
            True si se envió correctamente
        """
        from .email_templates import get_custom_email_template
        
        html = get_custom_email_template(
            title=title,
            header_text=header_text,
            greeting=greeting,
            main_content=main_content,
            button_text=button_text,
            button_url=button_url,
            footer_note=footer_note
        )
        
        return self._send_email(
            to=to,
            subject=title,
            html=html
        )


# Instancia global del servicio de email
email_service = EmailService()

