import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, Text, BigInteger, Integer, Enum as SAEnum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
from typing import TYPE_CHECKING
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
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    candidate_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    candidate_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    blob_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[ResumeStatus] = mapped_column(
        SAEnum(ResumeStatus, name="resume_status"), nullable=False
    )
    is_archived: Mapped[bool] = mapped_column(default=False, nullable=False)

    # --- Phase 4: extraction (populated by the Ollama pipeline). ---
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_status: Mapped[ResumeExtractionStatus] = mapped_column(
        SAEnum(ResumeExtractionStatus, name="resume_extraction_status"),
        default=ResumeExtractionStatus.PENDING, nullable=False,
    )
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    extracted_skills: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    extracted_experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_education: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    extracted_certifications: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    extracted_profile: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner: Mapped["User | None"] = relationship(foreign_keys=[owner_id])
    uploaded_by: Mapped["User"] = relationship(foreign_keys=[uploaded_by_id])