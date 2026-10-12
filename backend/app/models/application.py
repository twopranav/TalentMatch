import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, Float, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.user import User
    from app.models.job import Job
    from app.models.resume import Resume

class ApplicationStatus(str, PyEnum):
    APPLIED = "applied"
    UNDER_REVIEW = "under_review"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"
    HIRED = "hired"

class ShortlistStage(str, PyEnum):
    """Sub-state of an application whose status is SHORTLISTED. NULL on the
    application whenever its status is anything else."""
    SHORTLISTED = "shortlisted"  # default on entering the shortlist
    REVIEW = "review"
    INTERVIEW_SCHEDULED = "interview_scheduled"  # requires Application.interview_at
    REJECTED = "rejected"


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        # One application per user per job — re-applying is blocked at the DB
        # level, not just in route logic.
        UniqueConstraint("user_id", "job_id", name="uq_application_user_job"),
        # A recruiter-entered score is a 0-100 percentage like the AI score.
        # Enforced here too so no code path can store a nonsense value.
        CheckConstraint(
            "manual_score IS NULL OR (manual_score >= 0 AND manual_score <= 100)",
            name="ck_applications_manual_score_range",
        ),
        # Recruiter applicant list is "this job, best score first".
        Index("ix_applications_job_score", "job_id", "match_score"),
        # Shortlist tab: "this job, this status".
        Index("ix_applications_job_status", "job_id", "status"),
        # Recruiter-submitted applications have user_id NULL (the candidate
        # has no account), and NULLs never collide in uq_application_user_job
        # above. This partial index is what stops the same resume being
        # applied to the same job twice in that case.
        Index(
            "uq_application_job_resume_unowned",
            "job_id",
            "resume_id",
            unique=True,
            postgresql_where=text("user_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # NULL = applied on behalf of a candidate who has no account, by a
    # recruiter/admin/superuser from their resume library (see
    # routes/applications.py bulk_apply_resumes). submitted_by_id says who.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    resume_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[ApplicationStatus] = mapped_column(
        SAEnum(ApplicationStatus, name="application_status"), default=ApplicationStatus.APPLIED, nullable=False
    )
    # Only set while status == SHORTLISTED (see routes/applications.py).
    shortlist_stage: Mapped[ShortlistStage | None] = mapped_column(
        SAEnum(ShortlistStage, name="shortlist_stage"), nullable=True
    )
    # Only set while shortlist_stage == INTERVIEW_SCHEDULED. Timezone-aware.
    interview_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # --- Match score (app/core/semantic_match.py, app/core/matching_tasks.py) ---
    # NULL match_score = not scored yet. match_status: pending | done | failed.
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending", nullable=False)
    match_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    match_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # --- Manual score (recruiter-entered, optional) ---
    # Deliberately a SEPARATE column from match_score: the AI score is only
    # ever written by the scoring worker, and a recruiter's opinion is only
    # ever written by the manual-score endpoint, so a re-score can never
    # erase a human judgement. NULL = the recruiter hasn't entered one.
    # Recruiter-facing only: never put this on a candidate-facing schema.
    manual_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Two FKs point at users now, so every relationship has to say which.
    user: Mapped["User | None"] = relationship(back_populates="applications", foreign_keys=[user_id])
    submitted_by: Mapped["User | None"] = relationship(foreign_keys=[submitted_by_id])
    job: Mapped["Job"] = relationship(back_populates="applications")
    resume: Mapped["Resume | None"] = relationship()