import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class ApplicationNote(Base):
    """A recruiter's private note on one application.

    Its own table (not a column on applications) because an application
    collects many notes, from different recruiters, over time. Notes are
    append-only: the API can create and list them but never edits or deletes
    one, so what was written (and by whom) stays trustworthy. They go away
    only when their application is deleted (ON DELETE CASCADE).

    Recruiter-facing only: candidates must never be able to read these.
    """

    __tablename__ = "application_notes"
    __table_args__ = (
        # The popup asks for "this application's notes, newest first".
        Index("ix_application_notes_application", "application_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    # SET NULL + an email snapshot, same idea as AuditLog: deleting the
    # author's account must not delete (or be blocked by) their notes, and
    # the note should still say who wrote it.
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    author_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
