import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.job import (
    EmploymentType,
    JobExtractionStatus,
    JobStatus,
    RemoteType,
    SeniorityLevel,
)


from app.models.user import SubCompany


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

    # Recruiter-managed/manual values.
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

    # Recruiter-managed/manual values.
    required_skills: list[str] | None = None
    min_experience_years: int | None = None
    max_experience_years: int | None = None
    education_requirement: str | None = None

    closes_at: datetime | None = None

    # Only the superuser may choose; everyone else gets their own sub company.
    sub_company: SubCompany | None = None


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

    # Recruiter-managed/manual matching fields.
    required_skills: list[str] | None
    min_experience_years: int | None
    max_experience_years: int | None
    education_requirement: str | None

    published_at: datetime | None
    closes_at: datetime | None

    created_by_id: uuid.UUID
    sub_company: SubCompany | None = None
    created_at: datetime
    updated_at: datetime

    # -------------------------
    # Extraction results
    # -------------------------

    extraction_status: JobExtractionStatus
    extraction_error: str | None = None
    extracted_at: datetime | None = None

    # Every technical skill found in the JD.
    extracted_skills: list[str] | None = None

    # Only explicitly mandatory/compulsory skills.
    extracted_compulsory_skills: list[str] | None = None

    extracted_min_experience_years: int | None = None
    extracted_max_experience_years: int | None = None
    extracted_education_requirement: str | None = None

    extracted_profile: dict | None = None

    # -------------------------
    # Standalone skills-only extraction results (the live pipeline).
    # Mirrors ResumeRead's skills_* / experience_* block. The extraction_*
    # / extracted_* fields above belong to the deleted full-profile
    # extractor and stay empty.
    # -------------------------

    # Final validated skill list from app/core/jd_skills_extraction_tasks.py
    skills_result: list[str] | None = None
    skills_section_heading: str | None = None
    skills_extraction_status: JobExtractionStatus
    skills_extraction_error: str | None = None
    skills_extracted_at: datetime | None = None

    # Minimum experience the JD demands, in months. None = JD states no
    # requirement; 0 = entry-level/fresher marker.
    min_experience_months: int | None = None

    model_config = ConfigDict(from_attributes=True)


class JobSkillsUpdate(BaseModel):
    """Recruiter's corrected version of the JD's extracted skill list.
    Replaces Job.skills_result wholesale (add = new list has it, remove =
    new list lacks it), so the client always sends the full final list."""

    skills: list[str]

    @field_validator("skills")
    @classmethod
    def _clean_skills(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in value:
            skill = " ".join(raw.split())  # trim + collapse inner whitespace
            if not skill:
                continue
            if len(skill) > 100:
                raise ValueError("A skill must be 100 characters or fewer.")
            key = skill.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(skill)
        if not cleaned:
            raise ValueError("A job needs at least one skill to match against.")
        if len(cleaned) > 100:
            raise ValueError("A job can have at most 100 skills.")
        return cleaned
