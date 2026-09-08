import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, func, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class AuditLog(Base):
    """Append-only record of every create/update/delete on a job, user, or
    application. Rows are written in the same DB transaction as the mutation
    they describe (see app/core/audit.py: record_audit) so an audit entry
    and the change it documents always succeed or fail together. Application
    code never updates or deletes rows here.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_audit_logs_actor", "actor_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Nullable + ondelete="SET NULL": deleting the actor's account (or an
    # unauthenticated action like self-registration) must never delete, or
    # be blocked by, their audit history. actor_email is a point-in-time
    # snapshot so entries stay readable even after the actor row is gone or
    # their email later changes.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    action: Mapped[str] = mapped_column(String(50), nullable=False)  # "create" | "update" | "delete"
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "job" | "user" | "application"
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Full column-level snapshots, JSON-safe (enums -> .value, UUID/datetime
    # -> str). Sensitive/oversized columns are stripped before storage — see
    # _SNAPSHOT_EXCLUDE in app/core/audit.py. Both null on "create" for
    # `before` and on "delete" for `after` is not meaningful, since delete
    # actions only populate `before`.
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
