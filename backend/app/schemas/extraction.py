"""
Pydantic schemas for Phase 4 structured extraction.

These schemas are used for:
1. generating the structured-output schema sent to the Hugging Face
   Inference Provider, and
2. validating the provider response before it is persisted.

Extraction intentionally preserves source information. Normalization and
matching happen separately.
"""

from pydantic import BaseModel, Field


class EducationEntry(BaseModel):
    degree: str | None = None
    institution: str | None = None
    year: int | None = None


class WorkHistoryEntry(BaseModel):
    company: str | None = None
    title: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    duration: str | None = None


class ProjectEntry(BaseModel):
    name: str | None = None
    description: str | None = None


class CertificationEntry(BaseModel):
    name: str | None = None
    issuer: str | None = None
    year: int | None = None


class CandidateProfileExtraction(BaseModel):
    """
    Structured extraction result for a resume.

    experience_years is intentionally derived separately from work_history
    by the application. stated_experience preserves an explicit total-
    experience statement from the resume such as "5+" or "around seven years".
    """

    skills: list[str] = Field(default_factory=list)

    stated_experience: str | None = None

    # Derived by compute_experience_years() after extraction.
    experience_years: int | None = None

    education: list[EducationEntry] = Field(default_factory=list)

    certifications: list[CertificationEntry] = Field(default_factory=list)

    work_history: list[WorkHistoryEntry] = Field(default_factory=list)

    projects: list[ProjectEntry] = Field(default_factory=list)

    candidate_name: str | None = None
    candidate_email: str | None = None


class JobRequirementsExtraction(BaseModel):
    """
    Structured extraction result for a job description.

    skills:
        All concrete technical skills/competencies mentioned anywhere.

    compulsory_skills:
        Only skills that the JD explicitly marks as mandatory/required.
        This is the set used by the hard matching gate.
    """

    skills: list[str] = Field(default_factory=list)

    compulsory_skills: list[str] = Field(default_factory=list)

    min_experience_years: int | None = None

    max_experience_years: int | None = None

    education_requirement: str | None = None