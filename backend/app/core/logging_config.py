"""
Central logging setup shared by the API, the Celery worker and beat.

- JSON lines in production (one object per line, easy to ship to any log
  platform), readable text in development. Controlled by LOG_FORMAT:
  "auto" (default) = json when ENV=production, text otherwise.
- Every record carries a `request_id`. The API sets it per request
  (RequestLoggingMiddleware), the Celery wiring copies it into task
  messages, so one upload can be followed from the API into the worker.
- Log IDs and counts, never resume text, emails or other candidate PII.
"""
import json
import logging
import re
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from starlette.datastructures import MutableHeaders

from app.core.config import settings

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

REQUEST_ID_HEADER = "X-Request-ID"
# Only accept a caller-supplied ID if it is harmless to put in logs/headers.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

_SERVICE = "api"

# Attributes every LogRecord has; anything else came from `extra={...}`.
_STANDARD_ATTRS = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "request_id"}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "service": _SERVICE,
            "logger": record.name,
            "request_id": getattr(record, "request_id", None) or request_id_var.get(),
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _use_json() -> bool:
    mode = settings.LOG_FORMAT.strip().lower()
    if mode == "json":
        return True
    if mode == "text":
        return False
    return settings.IS_PRODUCTION


def setup_logging(service: str = "api") -> None:
    """Idempotent: safe to call from main.py and from Celery signals."""
    global _SERVICE
    _SERVICE = service

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    if _use_json():
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s"
            )
        )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL.upper())

    # uvicorn installs its own handlers; route them through ours instead.
    # Its access log is replaced by RequestLoggingMiddleware (one line per
    # request, with request_id and duration), so silence the duplicate.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # HTTP client libraries log full URLs (query strings included) at INFO.
    for name in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _incoming_request_id(scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            candidate = value.decode("latin-1")
            return candidate if _VALID_REQUEST_ID.match(candidate) else None
    return None


class RequestLoggingMiddleware:
    """Pure-ASGI middleware: assigns a request_id, echoes it in the
    X-Request-ID response header, and logs one line per request."""

    def __init__(self, app):
        self.app = app
        self.logger = logging.getLogger("app.request")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid.uuid4().hex
        token = request_id_var.set(request_id)

        started = time.perf_counter()
        status_code = 500
        failed = False

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", [])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            failed = True
            self.logger.exception("Unhandled error", extra=self._fields(scope, 500, started))
            raise
        finally:
            elapsed = time.perf_counter() - started
            path = scope.get("path", "")
            if path != "/metrics":
                try:
                    from app.core.metrics import observe_request, route_template

                    observe_request(
                        scope.get("method", ""),
                        route_template(scope),
                        500 if failed else status_code,
                        elapsed,
                    )
                except Exception:  # metrics must never break a request
                    pass
            if not failed:
                # Health probes are frequent and uninteresting.
                if (path.startswith("/api/health") or path == "/metrics") and status_code < 400:
                    level = logging.DEBUG
                elif status_code >= 500:
                    level = logging.WARNING
                else:
                    level = logging.INFO
                self.logger.log(
                    level, "request", extra=self._fields(scope, status_code, started)
                )
            request_id_var.reset(token)

    @staticmethod
    def _fields(scope, status_code: int, started: float) -> dict:
        client = scope.get("client")
        # Path only: query strings can hold search terms or emails.
        return {
            "method": scope.get("method"),
            "path": scope.get("path"),
            "status": status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "client_ip": client[0] if client else None,
        }
