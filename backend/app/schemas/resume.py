import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.resume import ResumeStatus

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
    # Populated by joining Resume.owner / Resume.uploaded_by in the route —
    # not on the ORM model itself, so this stays None unless the route sets
    # it explicitly (self-uploads have no candidate_name/candidate_email,
    # this is what lets the listing show *who* a resume belongs to).
    owner_email: str | None = None
    uploaded_by_email: str | None = None
    model_config = ConfigDict(from_attributes=True)

class ResumeReadWithUrl(ResumeRead):
    """Returned only from GET /resumes/{id} — the SAS URL is generated on
    demand and is short-lived, so it's never part of the plain list view."""
    download_url: str

class ResumeBulkUploadResult(BaseModel):
    """One entry per file submitted to POST /resumes/bulk. A bulk request
    always partially fails in practice (one bad file shouldn't sink the
    other 49), so the response reports per-file outcome instead of an
    all-or-nothing status."""
    original_filename: str
    success: bool
    resume: ResumeRead | None = None
    error: str | None = None