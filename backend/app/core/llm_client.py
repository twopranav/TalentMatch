"""
Resolves a task's active (provider, model) from the database and builds
the LangChain chat model for it, fresh on every call.

Deliberately not cached across calls: this backend runs multiple
uvicorn workers and separate Celery workers, each its own process with
its own memory -- a cache in one process would go stale the moment the
admin UI edits a row from a request another process handled, until that
process happened to restart. Skipping the cache means "change model" on
the website really does take effect on the very next extraction call,
everywhere, immediately. ChatOpenAI construction itself is cheap -- no
network call happens until .invoke() -- so this costs nothing in
practice.
"""

from app.core.llm_provider_registry import PROVIDERS, LLMConfigError    
from app.db.session import SessionLocal
from app.models.llm_config import LLMConfig


class UnknownProviderError(LLMConfigError):
    """Raised when a task has no llm_configs row, names a provider with
    no entry in PROVIDERS, or is still set to the "unset" placeholder
    left by the seed migration (no model has been chosen yet in the
    admin UI)."""


def get_chat_model_for_task(task: str):
    db = SessionLocal()
    try:
        row = db.query(LLMConfig).filter(LLMConfig.task == task).first()
    finally:
        db.close()

    if row is None:
        raise UnknownProviderError(
            f"No llm_configs row for task={task!r} -- seed one via the "
            f"admin UI or the seed migration."
        )

    build = PROVIDERS.get(row.provider)
    if build is None:
        raise UnknownProviderError(
            f"llm_configs row for task={task!r} has provider={row.provider!r} "
            f"/ model={row.model!r} -- pick a real provider+model for this "
            f"task via PUT /api/admin/llm-config/{task} before it can run."
        )

    return build(row.model)
