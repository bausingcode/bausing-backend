"""
Sistema de plantillas de email escalable para Bausing
"""
from datetime import datetime
from typing import Dict, Any, Optional

# Colores de la marca
BRAND_COLOR = "#00C1A7"
BRAND_COLOR_DARK = "#00a892"
WHITE = "#ffffff"
TEXT_DARK = "#333333"
TEXT_MEDIUM = "#666666"
TEXT_LIGHT = "#999999"
BG_LIGHT = "#f5f5f5"
BG_FOOTER = "#f9f9f9"

def get_base_email_structure(
    title: str,
    header_text: str,
    content_html: str,
    footer_text: Optional[str] = None
) -> str:
    """
    Genera la estructura base de un email con el diseño de Bausing.
    
    Args:
        title: Título del email (para el <title>)
        header_text: Texto que aparece en el header con fondo verde
        content_html: Contenido HTML principal del email
        footer_text: Texto adicional para el footer (opcional)
    
    Returns:
        HTML completo del email
    """
    current_year = datetime.now().year
    
    footer_content = f"""
                                <p style="margin: 0 0 10px; color: {TEXT_MEDIUM}; font-size: 14px;">
                                    © {current_year} Bausing. Todos los derechos reservados.
                                </p>
                                <p style="margin: 0; color: {TEXT_LIGHT}; font-size: 12px;">
                                    Si tienes alguna pregunta, no dudes en contactarnos.
                                </p>
    """
    
    if footer_text:
        footer_content += f"""
                                <p style="margin: 20px 0 0; color: {TEXT_LIGHT}; font-size: 12px;">
                                    {footer_text}
                                </p>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: {BG_LIGHT};">
        <table role="presentation" style="width: 100%; border-collapse: collapse; background-color: {BG_LIGHT};">
            <tr>
                <td align="center" style="padding: 40px 20px;">
                    <table role="presentation" style="max-width: 600px; width: 100%; border-collapse: collapse; background-color: {WHITE}; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                        <!-- Header -->
                        <tr>
                            <td style="padding: 40px 40px 30px; text-align: center; background: linear-gradient(135deg, {BRAND_COLOR} 0%, {BRAND_COLOR_DARK} 100%); border-radius: 12px 12px 0 0;">
                                <h1 style="margin: 0; color: {WHITE}; font-size: 32px; font-weight: 700; letter-spacing: -0.5px;">
                                    {header_text}
                                </h1>
                            </td>
                        </tr>
                        
                        <!-- Content -->
                        <tr>
                            <td style="padding: 40px;">
                                {content_html}
                            </td>
                        </tr>
                        
                        <!-- Footer -->
                        <tr>
                            <td style="padding: 30px 40px; text-align: center; background-color: {BG_FOOTER}; border-radius: 0 0 12px 12px;">
                                {footer_content}
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    return html


def get_button_html(text: str, url: str, style: Optional[str] = None) -> str:
    """
    Genera HTML para un botón CTA.
    
    Args:
        text: Texto del botón
        url: URL del enlace
        style: Estilos adicionales (opcional)
    
    Returns:
        HTML del botón
    """
    button_style = f"display: inline-block; padding: 16px 40px; background-color: {BRAND_COLOR}; color: {WHITE}; text-decoration: none; border-radius: 8px; font-size: 16px; font-weight: 600; text-align: center; transition: background-color 0.3s;"
    if style:
        button_style += style
    
    return f"""
    <table role="presentation" style="width: 100%; border-collapse: collapse; margin: 30px 0;">
        <tr>
            <td align="center" style="padding: 0;">
                <a href="{url}" style="{button_style}">
                    {text}
                </a>
            </td>
        </tr>
    </table>
    """


def get_text_link_html(text: str, url: str) -> str:
    """
    Genera HTML para un enlace de texto.
    
    Args:
        text: Texto del enlace
        url: URL del enlace
    
    Returns:
        HTML del enlace
    """
    return f"""
    <p style="margin: 30px 0 0; color: {TEXT_LIGHT}; font-size: 14px; line-height: 1.6;">
        {text}
    </p>
    <p style="margin: 10px 0 0; color: {BRAND_COLOR}; font-size: 12px; line-height: 1.6; word-break: break-all;">
        <a href="{url}" style="color: {BRAND_COLOR}; text-decoration: none;">{url}</a>
    </p>
    """


# ============================================
# PLANTILLAS ESPECÍFICAS DE EMAIL
# ============================================

def get_email_verification_template(user_first_name: str, verification_url: str) -> str:
    """
    Plantilla para email de verificación de cuenta.
    
    Args:
        user_first_name: Nombre del usuario
        verification_url: URL de verificación
    
    Returns:
        HTML completo del email
    """
    content = f"""
                                <p style="margin: 0 0 20px; color: {TEXT_DARK}; font-size: 16px; line-height: 1.6;">
                                    Hola <strong style="color: {BRAND_COLOR};">{user_first_name}</strong>,
                                </p>
                                <p style="margin: 0 0 30px; color: {TEXT_MEDIUM}; font-size: 16px; line-height: 1.6;">
                                    Gracias por registrarte en Bausing. Para completar tu registro y comenzar a disfrutar de nuestros servicios, por favor verifica tu dirección de email haciendo clic en el botón de abajo.
                                </p>
                                
                                {get_button_html("Verificar mi email", verification_url)}
                                
                                {get_text_link_html("Si el botón no funciona, copia y pega el siguiente enlace en tu navegador:", verification_url)}
                                
                                <p style="margin: 40px 0 0; color: {TEXT_LIGHT}; font-size: 12px; line-height: 1.6; border-top: 1px solid #eeeeee; padding-top: 30px;">
                                    Este enlace expirará en 7 días. Si no creaste una cuenta en Bausing, puedes ignorar este email de forma segura.
                                </p>
    """
    
    return get_base_email_structure(
        title="Verifica tu email - Bausing",
        header_text="¡Bienvenido a Bausing!",
        content_html=content
    )


def get_password_reset_template(user_first_name: str, reset_url: str, expires_in: str = "1 hora") -> str:
    """
    Plantilla para email de recuperación de contraseña.
    
    Args:
        user_first_name: Nombre del usuario
        reset_url: URL para resetear la contraseña
        expires_in: Tiempo de expiración del enlace
    
    Returns:
        HTML completo del email
    """
    content = f"""
                                <p style="margin: 0 0 20px; color: {TEXT_DARK}; font-size: 16px; line-height: 1.6;">
                                    Hola <strong style="color: {BRAND_COLOR};">{user_first_name}</strong>,
                                </p>
                                <p style="margin: 0 0 30px; color: {TEXT_MEDIUM}; font-size: 16px; line-height: 1.6;">
                                    Recibimos una solicitud para restablecer la contraseña de tu cuenta en Bausing. Si fuiste tú, haz clic en el botón de abajo para crear una nueva contraseña.
                                </p>
                                
                                {get_button_html("Restablecer contraseña", reset_url)}
                                
                                {get_text_link_html("Si el botón no funciona, copia y pega el siguiente enlace en tu navegador:", reset_url)}
                                
                                <p style="margin: 40px 0 0; color: {TEXT_LIGHT}; font-size: 12px; line-height: 1.6; border-top: 1px solid #eeeeee; padding-top: 30px;">
                                    Este enlace expirará en {expires_in}. Si no solicitaste restablecer tu contraseña, puedes ignorar este email de forma segura.
                                </p>
    """
    
    return get_base_email_structure(
        title="Restablecer contraseña - Bausing",
        header_text="Restablecer contraseña",
        content_html=content
    )


def get_order_confirmation_template(
    user_first_name: str,
    order_number: str,
    order_total: str,
    order_url: Optional[str] = None
) -> str:
    """
    Plantilla para email de confirmación de pedido.
    
    Args:
        user_first_name: Nombre del usuario
        order_number: Número de pedido
        order_total: Total del pedido
        order_url: URL para ver el pedido (opcional)
    
    Returns:
        HTML completo del email
    """
    button_html = ""
    if order_url:
        button_html = get_button_html("Ver mi pedido", order_url)
    
    content = f"""
                                <p style="margin: 0 0 20px; color: {TEXT_DARK}; font-size: 16px; line-height: 1.6;">
                                    Hola <strong style="color: {BRAND_COLOR};">{user_first_name}</strong>,
                                </p>
                                <p style="margin: 0 0 30px; color: {TEXT_MEDIUM}; font-size: 16px; line-height: 1.6;">
                                    ¡Gracias por tu compra! Tu pedido ha sido confirmado y está siendo procesado.
                                </p>
                                
                                <div style="background-color: {BG_FOOTER}; padding: 20px; border-radius: 8px; margin: 20px 0;">
                                    <p style="margin: 0 0 10px; color: {TEXT_DARK}; font-size: 14px; font-weight: 600;">
                                        Número de pedido: <span style="color: {BRAND_COLOR};">{order_number}</span>
                                    </p>
                                    <p style="margin: 0; color: {TEXT_DARK}; font-size: 14px; font-weight: 600;">
                                        Total: <span style="color: {BRAND_COLOR};">{order_total}</span>
                                    </p>
                                </div>
                                
                                {button_html}
                                
                                <p style="margin: 30px 0 0; color: {TEXT_MEDIUM}; font-size: 14px; line-height: 1.6;">
                                    Te notificaremos cuando tu pedido sea enviado.
                                </p>
    """
    
    return get_base_email_structure(
        title="Confirmación de pedido - Bausing",
        header_text="¡Pedido confirmado!",
        content_html=content
    )


def get_welcome_template(user_first_name: str, dashboard_url: Optional[str] = None) -> str:
    """
    Plantilla para email de bienvenida.
    
    Args:
        user_first_name: Nombre del usuario
        dashboard_url: URL del dashboard (opcional)
    
    Returns:
        HTML completo del email
    """
    button_html = ""
    if dashboard_url:
        button_html = get_button_html("Ir a mi cuenta", dashboard_url)
    
    content = f"""
                                <p style="margin: 0 0 20px; color: {TEXT_DARK}; font-size: 16px; line-height: 1.6;">
                                    Hola <strong style="color: {BRAND_COLOR};">{user_first_name}</strong>,
                                </p>
                                <p style="margin: 0 0 30px; color: {TEXT_MEDIUM}; font-size: 16px; line-height: 1.6;">
                                    ¡Bienvenido a Bausing! Estamos emocionados de tenerte con nosotros. Ahora puedes explorar nuestros productos y comenzar a comprar.
                                </p>
                                
                                {button_html}
                                
                                <p style="margin: 30px 0 0; color: {TEXT_MEDIUM}; font-size: 14px; line-height: 1.6;">
                                    Si tienes alguna pregunta, nuestro equipo de soporte está aquí para ayudarte.
                                </p>
    """
    
    return get_base_email_structure(
        title="Bienvenido a Bausing",
        header_text="¡Bienvenido a Bausing!",
        content_html=content
    )


def get_custom_email_template(
    title: str,
    header_text: str,
    greeting: str,
    main_content: str,
    button_text: Optional[str] = None,
    button_url: Optional[str] = None,
    footer_note: Optional[str] = None
) -> str:
    """
    Plantilla genérica para crear emails personalizados.
    
    Args:
        title: Título del email
        header_text: Texto del header
        greeting: Saludo personalizado (ej: "Hola Juan,")
        main_content: Contenido principal del email
        button_text: Texto del botón CTA (opcional)
        button_url: URL del botón CTA (opcional)
        footer_note: Nota adicional para el footer (opcional)
    
    Returns:
        HTML completo del email
    """
    button_html = ""
    if button_text and button_url:
        button_html = get_button_html(button_text, button_url)
    
    content = f"""
                                <p style="margin: 0 0 20px; color: {TEXT_DARK}; font-size: 16px; line-height: 1.6;">
                                    {greeting}
                                </p>
                                <div style="margin: 0 0 30px; color: {TEXT_MEDIUM}; font-size: 16px; line-height: 1.6;">
                                    {main_content}
                                </div>
                                
                                {button_html}
    """
    
    if footer_note:
        content += f"""
                                <p style="margin: 40px 0 0; color: {TEXT_LIGHT}; font-size: 12px; line-height: 1.6; border-top: 1px solid #eeeeee; padding-top: 30px;">
                                    {footer_note}
                                </p>
        """
    
    return get_base_email_structure(
        title=title,
        header_text=header_text,
        content_html=content,
        footer_text=footer_note
    )

