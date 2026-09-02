import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.job import JobStatus

class JobCreate(BaseModel):
    title: str
    description: str | None = None

class JobUpdate(BaseModel):
    # every field optional — a PATCH should be able to send just one field
    title: str | None = None
    description: str | None = None
    status: JobStatus | None = None

class JobRead(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    jd_raw_text: str | None         
    status: JobStatus
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)