"""
Pydantic schemas for Phase 4 structured extraction. These serve double
duty: (1) the JSON schema handed to Ollama's structured-output mode, so
the model is constrained to this exact shape, and (2) the validation
target for parsing Ollama's response before it's written to the DB.
"""
from pydantic import BaseModel, Field


class EducationEntry(BaseModel):
    degree: str | None = None
    institution: str | None = None
    year: int | None = None


class WorkHistoryEntry(BaseModel):
    company: str | None = None
    title: str | None = None
    start_date: str | None = None  # kept as free text (e.g. "2021-06" or
                                    # "Jun 2021") — resumes rarely give
                                    # clean ISO dates, and forcing one here
                                    # would just make the model invent it
    end_date: str | None = None    # None/"" may mean "current" — see note
                                    # in extracted_profile.is_current if you
                                    # need that distinguished later


class ProjectEntry(BaseModel):
    name: str | None = None
    description: str | None = None


class CandidateProfileExtraction(BaseModel):
    """Result of extracting a resume. Top-level fields here map directly
    onto the promoted columns on Resume; everything is also stored
    wholesale in Resume.extracted_profile as the source of truth."""
    skills: list[str] = Field(default_factory=list)
    experience_years: int | None = None  # computed by the model from the
                                          # work history date ranges, not a
                                          # verbatim span — flag low
                                          # confidence results for review
                                          # once you have a UI for that
    education: list[EducationEntry] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    work_history: list[WorkHistoryEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    candidate_name: str | None = None
    candidate_email: str | None = None


class JobRequirementsExtraction(BaseModel):
    """Result of extracting a JD. required_skills / preferred_skills are
    kept as separate lists because your PRD calls out 'mandatory vs
    preferred requirements' as its own Phase 4/5 deliverable — this is
    where that distinction gets made, at extraction time, while the model
    still has the full JD text and phrasing in front of it."""
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    min_experience_years: int | None = None
    max_experience_years: int | None = None
    education_requirement: str | None = None