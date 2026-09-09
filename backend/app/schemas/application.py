import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.application import ApplicationStatus

class ApplicationCreate(BaseModel):
    job_id: uuid.UUID
    # Optional and effectively unused: the apply route always resolves the
    # applicant's own active resume itself. Needs a default, otherwise a
    # nullable field with no default is still *required* to pydantic v2,
    # so any request that omits resume_id (as the frontend does) 422s.
    resume_id: uuid.UUID | None = None

class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus

class ApplicationRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID
    resume_id: uuid.UUID | None
    status: ApplicationStatus
    applied_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

# "My applications" view — includes enough job context that the frontend
# doesn't need a second round trip per row.
class ApplicationWithJob(ApplicationRead):
    job_title: str
    job_status: str
    location: str | None
    company : str | None

# Recruiter/admin "who applied" view.
class ApplicationWithApplicant(ApplicationRead):
    applicant_email: str
    applicant_name: str | None
    resume_filename: str | None = None