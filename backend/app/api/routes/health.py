from fastapi import APIRouter, Depends
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