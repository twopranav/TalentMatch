import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, Text, Integer, Enum as SAEnum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.user import User
    from app.models.application import Application

class JobStatus(str, PyEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"

class EmploymentType(str, PyEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"

class SeniorityLevel(str, PyEnum):
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    EXECUTIVE = "executive"

class RemoteType(str, PyEnum):
    ONSITE = "onsite"
    REMOTE = "remote"
    HYBRID = "hybrid"

class JobExtractionStatus(str, PyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"

class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    jd_raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status"), default=JobStatus.DRAFT, nullable=False
    )

    # --- filtering / listing fields ---
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employment_type: Mapped[EmploymentType] = mapped_column(
        SAEnum(EmploymentType, name="employment_type"),
        default=EmploymentType.FULL_TIME,
        nullable=False,
    )
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seniority: Mapped[SeniorityLevel | None] = mapped_column(
        SAEnum(SeniorityLevel, name="seniority_level"), nullable=True
    )
    remote_type: Mapped[RemoteType | None] = mapped_column(
        SAEnum(RemoteType, name="remote_type"), nullable=True
    )
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- matching-engine fields (populated later by Phase 4/5, columns exist now) ---
    # JSONB over Text so Postgres can index/query it later without a type migration
    required_skills: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    min_experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    education_requirement: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Phase 4: extraction (populated by the Ollama pipeline). Kept
    # SEPARATE from required_skills / min_experience_years / max_experience_years /
    # education_requirement above, which are recruiter-editable via
    # JobCreate/JobUpdate — extraction must never silently overwrite a
    # value a recruiter typed in by hand. Phase 5/6 decide how these two
    # sets combine (e.g. "use extracted_* only where the recruiter left
    # the manual field blank"); storage keeps them independent regardless.
    extraction_status: Mapped[JobExtractionStatus] = mapped_column(
        SAEnum(JobExtractionStatus, name="job_extraction_status"),
        default=JobExtractionStatus.PENDING, nullable=False,
    )
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    extracted_required_skills: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    extracted_min_experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_max_experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_education_requirement: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extracted_profile: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # --- lifecycle fields ---
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    closes_at: Mapped[datetime | None] = mapped_column(nullable=True)

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by: Mapped["User"] = relationship(back_populates="jobs")
    applications: Mapped[list["Application"]] = relationship(back_populates="job", cascade="all, delete-orphan")