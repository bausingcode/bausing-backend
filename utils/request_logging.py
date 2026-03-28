"""
Logging de peticiones HTTP y errores no capturados (compatible con stdout en producción).
"""
import logging
import sys
import time

from flask import Flask, g, request, got_request_exception
from werkzeug.exceptions import HTTPException


def configure_app_logging(app: Flask) -> None:
    """Nivel global, formato y menos ruido del logger de Werkzeug (evita duplicar cada línea)."""
    level_name = app.config.get("LOG_LEVEL", "INFO")
    level = getattr(logging, str(level_name).upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    app.logger.setLevel(level)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def init_request_logging(app: Flask) -> None:
    """Registra logs por request (método, ruta, status, duración) y excepciones."""

    @app.before_request
    def _request_timer_start():
        g._request_started = time.perf_counter()

    @app.after_request
    def _access_log(response):
        if getattr(request, "routing_exception", None):
            return response
        path = request.path or ""
        if path == "/favicon.ico":
            return response

        started = getattr(g, "_request_started", None)
        duration_ms = (time.perf_counter() - started) * 1000 if started is not None else 0.0

        app.logger.info(
            "%s %s %s %.1fms",
            request.method,
            path,
            response.status_code,
            duration_ms,
        )
        return response

    def _log_exception(sender, **kwargs):
        exception = kwargs.get("exception")
        if exception is None:
            return
        # Sin contexto de request válido: solo loguear el error
        try:
            method = request.method
            path = request.path
        except RuntimeError:
            sender.logger.exception("Exception outside request context: %s", exception)
            return

        if isinstance(exception, HTTPException):
            code = exception.code or 0
            if code >= 500:
                sender.logger.error(
                    "%s %s -> HTTP %s %s",
                    method,
                    path,
                    code,
                    exception.description,
                    exc_info=exception,
                )
            elif code >= 400:
                sender.logger.warning(
                    "%s %s -> HTTP %s %s",
                    method,
                    path,
                    code,
                    getattr(exception, "description", exception),
                )
            return

        sender.logger.exception("%s %s -> unhandled exception", method, path)

    got_request_exception.connect(_log_exception, app)
