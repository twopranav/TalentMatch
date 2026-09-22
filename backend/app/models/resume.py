import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


class ResumeStatus(str, PyEnum):
    UPLOADED = "UPLOADED"
    FAILED = "FAILED"


class ResumeExtractionStatus(str, PyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    candidate_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    candidate_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    original_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    content_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    blob_path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    status: Mapped[ResumeStatus] = mapped_column(
        SAEnum(ResumeStatus, name="resume_status"),
        nullable=False,
    )

    is_archived: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    # -------------------------
    # Extraction
    # -------------------------

    raw_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    extraction_status: Mapped[ResumeExtractionStatus] = mapped_column(
        SAEnum(
            ResumeExtractionStatus,
            name="resume_extraction_status",
        ),
        default=ResumeExtractionStatus.PENDING,
        nullable=False,
    )

    extraction_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    extracted_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )

    extracted_skills: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Explicit statement from the resume such as:
    # "5+ years", "around seven years", "8 years".
    extracted_stated_experience: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Derived from work_history by compute_experience_years().
    extracted_experience_years: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    extracted_education: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    extracted_certifications: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    extracted_profile: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # -------------------------
    # Standalone skills-only extraction (separate from extracted_skills
    # above, which belongs to the full-profile call). See
    # app/core/skills_extraction_tasks.py -- own status lifecycle so a
    # full-profile success/failure never fights this pipeline for the
    # same column.
    # -------------------------

    skills_result: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    skills_section_heading: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    skills_extraction_status: Mapped[ResumeExtractionStatus] = mapped_column(
        SAEnum(
            ResumeExtractionStatus,
            name="resume_extraction_status",
        ),
        default=ResumeExtractionStatus.PENDING,
        nullable=False,
    )

    skills_extraction_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    skills_extracted_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )

    # Incremented only by the fault-handling sweep (never by the task
    # itself on a normal run) each time it redispatches this row after
    # finding it PENDING past the stale window or FAILED. Caps how many
    # times a row can come back from failure on its own before it's left
    # for a human / re-upload -- see extraction_retry_sweep.py.
    skills_extraction_retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # -------------------------
    # Lifecycle
    # -------------------------

    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    owner: Mapped["User | None"] = relationship(
        foreign_keys=[owner_id],
    )

    uploaded_by: Mapped["User"] = relationship(
        foreign_keys=[uploaded_by_id],
    )