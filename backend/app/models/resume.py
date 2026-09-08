import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, Integer, BigInteger, Boolean, Enum as SAEnum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.user import User

class ResumeStatus(str, PyEnum):
    """Phase 3 scope only: did the file make it into blob storage intact.
    Text extraction / structured parsing gets its own status field on this
    model in Phase 4 — deliberately not reusing this one, so a parsing
    failure can never be confused with an upload failure."""
    UPLOADED = "uploaded"
    FAILED = "failed"

class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # The candidate this resume belongs to. Nullable because a
    # recruiter-sourced bulk upload may not correspond to an existing
    # account yet — Phase 4/5 can backfill this once a candidate is
    # identified or registers.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Who actually performed the upload (always set). For self-upload this
    # equals owner_id; for recruiter sourcing it's the recruiter/admin.
    # Kept separate from owner_id so audit/ownership logic never has to
    # guess which case it's in.
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Captured at upload time only for sourced resumes with no account yet.
    # Left null for self-uploads (owner_id already identifies the person).
    # Phase 4 parsing may populate/correct these once it reads the file.
    candidate_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    candidate_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Key *within* the container, not a full URL — a container rename or
    # SAS rotation never orphans a stored link, because download URLs are
    # generated on demand from this path rather than stored directly.
    blob_path: Mapped[str] = mapped_column(String(1000), nullable=False)

    status: Mapped[ResumeStatus] = mapped_column(
        SAEnum(ResumeStatus, name="resume_status"), default=ResumeStatus.UPLOADED, nullable=False
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner: Mapped["User | None"] = relationship(foreign_keys=[owner_id])
    uploaded_by: Mapped["User"] = relationship(foreign_keys=[uploaded_by_id])
