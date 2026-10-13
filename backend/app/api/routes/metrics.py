"""GET /metrics for Prometheus. Not part of /api and not in the OpenAPI docs.

Access: in development it is open. In production it is disabled (404)
unless METRICS_TOKEN is set, and then needs `Authorization: Bearer <token>`.
Also keep it off the public internet at your reverse proxy.
"""
import hmac

from fastapi import APIRouter, HTTPException, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.config import settings
from app.core.metrics import register_collector

router = APIRouter(include_in_schema=False)

register_collector()


@router.get("/metrics")
def metrics(request: Request) -> Response:
    token = settings.METRICS_TOKEN
    if token:
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied, f"Bearer {token}"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    elif settings.IS_PRODUCTION:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
