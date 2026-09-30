from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.audit import record_audit, snapshot
from app.core.deps import require_admin_or_superuser
import time
from app.core.llm_client import get_chat_model_for_task
from app.core.llm_json_call import content_to_text
from app.core.llm_provider_registry import PROVIDERS, LLMConfigError
from app.db.session import get_db
from app.models.llm_config import LLMConfig
from app.models.user import User
from app.schemas.llm_config import LLMConfigRead, LLMConfigUpdate

router = APIRouter()


@router.get("", response_model=list[LLMConfigRead])
def list_llm_configs(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_superuser),
):
    return db.query(LLMConfig).order_by(LLMConfig.task).all()


@router.get("/providers", response_model=list[str])
def list_providers(_: User = Depends(require_admin_or_superuser)):
    """Populates the provider dropdown on the admin page."""
    return sorted(PROVIDERS)


@router.put("/{task}", response_model=LLMConfigRead)
def update_llm_config(
    task: str,
    payload: LLMConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_superuser),
):
    row = db.query(LLMConfig).filter(LLMConfig.task == task).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No llm_configs row for task {task!r}.",
        )

    before = snapshot(row, "llm_config")
    row.provider = payload.provider
    row.model = payload.model
    db.commit()
    db.refresh(row)
    record_audit(
        db,
        actor=current_user,
        action="update",
        resource_type="llm_config",
        resource_id=row.id,
        before=before,
        after=snapshot(row, "llm_config"),
    )
    db.commit()

    return row


@router.post("/{task}/probe")
def probe_llm_config(
    task: str,
    _: User = Depends(require_admin_or_superuser),
):
    """Makes one tiny real call with the task's configured provider/model.
    Admin-only because it spends provider quota."""
    started = time.monotonic()
    try:
        reply = get_chat_model_for_task(task).invoke("Reply with exactly: ok")
    except LLMConfigError as exc:
        return {"ok": False, "stage": "config", "error": str(exc)}
    except Exception as exc:
        return {
            "ok": False,
            "stage": "provider_call",
            "error": f"{type(exc).__name__}: {exc}",
        }

    return {
        "ok": True,
        "elapsed_s": round(time.monotonic() - started, 2),
        "reply": content_to_text(reply.content)[:80],
    }
