import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.job import JobStatus, EmploymentType, SeniorityLevel, RemoteType, JobExtractionStatus

class JobCreate(BaseModel):
    title: str
    description: str | None = None
    location: str | None = None
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    department: str | None = None
    seniority: SeniorityLevel | None = None
    remote_type: RemoteType | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    required_skills: list[str] | None = None
    min_experience_years: int | None = None
    max_experience_years: int | None = None
    education_requirement: str | None = None
    closes_at: datetime | None = None

class JobUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: JobStatus | None = None
    location: str | None = None
    employment_type: EmploymentType | None = None
    department: str | None = None
    seniority: SeniorityLevel | None = None
    remote_type: RemoteType | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    required_skills: list[str] | None = None
    min_experience_years: int | None = None
    max_experience_years: int | None = None
    education_requirement: str | None = None
    closes_at: datetime | None = None

class JobRead(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    jd_raw_text: str | None
    status: JobStatus
    location: str | None
    employment_type: EmploymentType
    department: str | None
    seniority: SeniorityLevel | None
    remote_type: RemoteType | None
    salary_min: int | None
    salary_max: int | None
    required_skills: list[str] | None
    min_experience_years: int | None
    max_experience_years: int | None
    education_requirement: str | None
    published_at: datetime | None
    closes_at: datetime | None
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    # --- Phase 4: extraction results, kept separate from the
    # recruiter-editable required_skills/min_experience_years/etc. above —
    # see the model's comment on why these never overwrite each other. ---
    extraction_status: JobExtractionStatus
    extraction_error: str | None = None
    extracted_at: datetime | None = None
    extracted_required_skills: list[str] | None = None
    extracted_min_experience_years: int | None = None
    extracted_max_experience_years: int | None = None
    extracted_education_requirement: str | None = None
    extracted_profile: dict | None = None
    model_config = ConfigDict(from_attributes=True)