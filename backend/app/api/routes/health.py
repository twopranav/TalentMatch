from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
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