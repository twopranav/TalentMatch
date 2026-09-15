import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.resume import ResumeExtractionStatus, ResumeStatus


class ResumeRead(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID | None
    uploaded_by_id: uuid.UUID

    candidate_name: str | None
    candidate_email: str | None

    original_filename: str
    content_type: str
    size_bytes: int

    status: ResumeStatus
    is_archived: bool

    created_at: datetime
    updated_at: datetime

    # Populated by joining Resume.owner / Resume.uploaded_by in the route.
    owner_email: str | None = None
    uploaded_by_email: str | None = None

    # -------------------------
    # Extraction results
    # -------------------------

    extraction_status: ResumeExtractionStatus
    extraction_error: str | None = None
    extracted_at: datetime | None = None

    extracted_skills: list[str] | None = None

    extracted_stated_experience: str | None = None

    extracted_experience_years: int | None = None

    extracted_education: list | None = None

    extracted_certifications: list | None = None

    extracted_profile: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class ResumeReadWithUrl(ResumeRead):
    """
    Returned only from GET /resumes/{id}.

    The download URL is generated on demand.
    """

    download_url: str


class ResumeBulkUploadResult(BaseModel):
    """
    One entry per file submitted to POST /resumes/bulk.

    A bulk request can partially fail, so each file gets its own result.
    """

    original_filename: str
    success: bool
    resume: ResumeRead | None = None
    error: str | None = None