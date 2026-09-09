import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.application import ApplicationStatus

class ApplicationCreate(BaseModel):
    job_id: uuid.UUID

class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus

class ApplicationRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID
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