import uuid
from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class LLMConfig(Base):
    """
    One row per extraction task, holding the active provider+model for
    that task. Edited through /api/admin/llm-config -- changing a row
    takes effect on the very next extraction call, no deploy needed.
    Credentials/endpoints (HF_TOKEN, OPENAI_API_KEY, ...) stay in
    environment settings, never here -- this table only ever holds the
    provider name + model id, matching the registry in
    app/core/llm_provider_registry.py.

    provider/model can be "unset" -- the migration seeds rows this way
    when no default model has been chosen yet. get_chat_model_for_task()
    treats "unset" the same as an unknown provider: it raises rather
    than silently building a client, so a task with no model picked
    fails loudly (in extraction logs / /health/llm) instead of quietly
    calling nothing.
    """

    __tablename__ = "llm_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )
