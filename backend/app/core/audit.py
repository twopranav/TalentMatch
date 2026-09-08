"""
Audit logging helper. Every route that creates/updates/deletes a job, user,
or application calls record_audit() alongside its normal db.add/delete —
see app/api/routes/jobs.py, users.py, applications.py, and the user-mutating
endpoints in auth.py for the call sites.
"""
import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User

# Columns never captured in a snapshot, keyed by resource_type: either too
# large to store cheaply on every mutation (raw JD text) or security-
# sensitive (password hash). Everything else on the model is captured.
_SNAPSHOT_EXCLUDE: dict[str, set[str]] = {
    "job": {"jd_raw_text"},
    "user": {"hashed_password"},
    "application": set(),
}


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def snapshot(instance: Any, resource_type: str) -> dict[str, Any]:
    """Serialize an ORM instance's own columns (not relationships) into a
    JSON-safe dict for storage as a before/after audit snapshot. Call this
    BEFORE mutating an instance to capture `before`, and after
    db.flush()/db.refresh() to capture `after`.
    """
    excluded = _SNAPSHOT_EXCLUDE.get(resource_type, set())
    mapper = inspect(instance).mapper
    return {
        col.key: _serialize_value(getattr(instance, col.key))
        for col in mapper.column_attrs
        if col.key not in excluded
    }


def record_audit(
    db: Session,
    *,
    actor: Optional[User],
    action: str,
    resource_type: str,
    resource_id: uuid.UUID,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
) -> AuditLog:
    """Stage an audit log row on the given session. Does NOT call db.commit()
    — it rides along in the caller's existing transaction, so the audit
    entry and the mutation it describes always succeed or fail together.
    actor=None is valid and expected for unauthenticated actions (e.g. a
    new account self-registering).
    """
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before=before,
        after=after,
    )
    db.add(entry)
    return entry
