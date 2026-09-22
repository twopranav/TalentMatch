from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
import httpx
from app.core.config import settings
from app.db.session import get_db

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
def health_check_llm() -> dict:
    """
    Confirms the API can reach the local Ollama server and that the
    extraction model is actually pulled -- not just that the container
    is up. A resume/JD extraction failure that traces back to "Ollama
    container never finished pulling the model" or "Ollama container is
    down" should show up here instead of only as a pile of FAILED
    extraction rows discovered later.
    """
    base_url = settings.OLLAMA_BASE_URL.rstrip("/")
    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=5)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return {"status": "error", "llm": "unreachable", "detail": str(exc)}

    models = [m["name"] for m in response.json().get("models", [])]
    expected = settings.HF_EXTRACTION_MODEL

    if expected not in models:
        return {
            "status": "error",
            "llm": "reachable",
            "model": "not pulled",
            "expected": expected,
            "available": models,
        }

    return {"status": "ok", "llm": "reachable", "model": "ready"}