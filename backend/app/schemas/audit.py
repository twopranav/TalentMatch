import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_email: str | None
    action: str  # "create" | "update" | "delete"
    resource_type: str  # "job" | "user" | "application" | "application_note" | "resume"
    resource_id: uuid.UUID
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    # Names of the fields whose value differs between before and after, so a
    # UI can render "status: applied -> shortlisted" without diffing JSON.
    # Empty for create/delete rows.
    changed_fields: list[str] = []
    created_at: datetime
