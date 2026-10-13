from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.llm_config import LLMConfig

router = APIRouter(tags=["health"])

@router.get("/health")
def health_check() -> dict:
    """Basic liveness check — API is up."""
    return {"status": "ok"}

@router.get("/health/db")
def health_check_db(db: Session = Depends(get_db)) -> dict:
    """Confirms the API can actually reach Postgres, not just that the process is alive."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}

@router.get("/health/llm")
def health_check_llm(db: Session = Depends(get_db)) -> dict:
    """
    Reports the provider/model currently configured for each extraction
    task (set via PUT /api/admin/llm-config/{task}). No network call is
    made here -- hosted providers (OpenAI, HF Inference Providers) have
    no local "is it pulled" check the way a self-hosted model did;
    a bad credential or unreachable provider surfaces as an extraction
    failure instead. This just confirms every task actually has a real
    provider+model chosen, not the "unset" seed placeholder.
    """
    configs = db.query(LLMConfig).order_by(LLMConfig.task).all()
    if not configs:
        return {"status": "error", "detail": "No llm_configs rows found — run migrations."}

    unset = [c.task for c in configs if c.provider == "unset" or c.model == "unset"]
    result = {
        "status": "error" if unset else "ok",
        "configs": [{"task": c.task, "provider": c.provider, "model": c.model} for c in configs],
    }
    if unset:
        result["unset_tasks"] = unset
    return result


@router.get("/health/redis")
def health_check_redis():
    """Redis is the Celery broker and the rate-limit store, so if it is down
    nothing queued will run. 503 on failure so uptime monitors catch it."""
    from app.core.metrics import _redis

    try:
        _redis().ping()
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "redis": "unreachable", "detail": type(exc).__name__},
        )
    return {"status": "ok", "redis": "connected"}


@router.get("/health/worker")
def health_check_worker():
    """Is at least one Celery worker alive and answering, and how many
    messages are waiting? 503 if no worker responds (extractions would sit
    at PENDING until one comes back)."""
    from app.core.celery_app import celery_app
    from app.core.metrics import _redis, queue_names

    try:
        replies = celery_app.control.inspect(timeout=1.5).ping() or {}
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "workers": [], "detail": type(exc).__name__},
        )

    depths: dict[str, int] = {}
    try:
        r = _redis()
        depths = {name: int(r.llen(name)) for name in queue_names()}
    except Exception:
        pass  # queue depth is a bonus; worker liveness is the point

    if not replies:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "workers": [], "queues": depths, "detail": "no worker responded"},
        )
    return {"status": "ok", "workers": sorted(replies), "queues": depths}
