"""GET /metrics for Prometheus. Not part of /api and not in the OpenAPI docs.

Access: in development it is open. In production it is disabled (404)
unless METRICS_TOKEN is set, and then needs `Authorization: Bearer <token>`.
Also keep it off the public internet at your reverse proxy.
"""
import hmac

from fastapi import APIRouter, HTTPException, Request, Response, status, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.deps import require_admin_or_superuser
from app.db.session import get_db
from app.models.job import Job
from app.models.resume import Resume, ResumeExtractionStatus
from app.models.user import User
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


# Not on `router`: that one is hidden from the OpenAPI docs and has no auth,
# while this endpoint is documented and admin-only.
admin_router = APIRouter()


@admin_router.get("/api/v1/admin/health-metrics")
def health_metrics(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_superuser),
):
    """Live system snapshot for the admin dashboard. Built from the same
    helpers that feed /metrics, so the two never disagree."""
    from app.core import metrics as m
    from app.models.llm_config import LLMConfig

    try:
        stuck = dict(m._count_stuck_rows(use_cache=False))
    except Exception:
        stuck = {}
    # Rows actively being worked on right now (not necessarily stuck).
    stuck["resume_extractions"] = db.query(func.count(Resume.id)).filter(
        Resume.extraction_status == ResumeExtractionStatus.PROCESSING
    ).scalar() or 0
    stuck["job_extractions"] = db.query(func.count(Job.id)).filter(
        Job.skills_extraction_status == "processing"
    ).scalar() or 0

    depths = m.queue_depths()
    probes = m.last_probe_results()
    tasks = []
    for row in db.query(LLMConfig).order_by(LLMConfig.task).all():
        tasks.append({
            "task": row.task,
            "provider": row.provider,
            "model": row.model,
            "configured": row.provider != "unset" and row.model != "unset",
            "last_probe": probes.get(row.task),
        })

    return {
        "queue_depth": depths["total"] if depths else None,
        "queues": depths["queues"] if depths else {},
        "quota_window_usage": m.quota_snapshot(),
        "stuck_rows": stuck,
        "redis_status": m.redis_status(),
        "llm_task_results": tasks,
    }
