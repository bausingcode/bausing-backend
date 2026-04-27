from app import app
from asgiref.wsgi import WsgiToAsgi
import os

# Convertir la aplicación Flask (WSGI) a ASGI para usar con Hypercorn
asgi_app = WsgiToAsgi(app)

if __name__ == '__main__':
    # Si se ejecuta directamente, usar el servidor de desarrollo de Flask (un solo proceso).
    # Producción: Gunicorn (varios workers) o Hypercorn -w N — ver CLAUDE.md sección Concurrencia.
    app.run(debug=True, host='0.0.0.0', port=5050)

