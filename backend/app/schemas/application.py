import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.application import ApplicationStatus, InterviewStage, ShortlistStage

class ApplicationCreate(BaseModel):
    job_id: uuid.UUID
    # Optional and effectively unused: the apply route always resolves the
    # applicant's own active resume itself. Needs a default, otherwise a
    # nullable field with no default is still *required* to pydantic v2,
    # so any request that omits resume_id (as the frontend does) 422s.
    resume_id: uuid.UUID | None = None

class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus

class ShortlistStageUpdate(BaseModel):
    stage: ShortlistStage
    # Required (and must carry a timezone / UTC offset) when stage is
    # interview_scheduled; ignored and cleared for every other stage.
    interview_at: datetime | None = None

    @model_validator(mode="after")
    def _check_interview_at(self):
        if self.stage == ShortlistStage.INTERVIEW_SCHEDULED:
            if self.interview_at is None:
                raise ValueError("interview_at is required when stage is interview_scheduled")
            if self.interview_at.tzinfo is None:
                raise ValueError("interview_at must include a timezone offset (e.g. 2026-10-20T14:30:00Z)")
        else:
            self.interview_at = None
        return self


class InterviewUpdate(BaseModel):
    stage: InterviewStage
    interview_at: datetime | None = None  # omit to keep the current date

    @model_validator(mode="after")
    def _tz_required(self):
        if self.interview_at is not None and self.interview_at.tzinfo is None:
            raise ValueError("interview_at must include a timezone offset (e.g. 2026-10-20T14:30:00Z)")
        return self


class ApplicationRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None  # None = submitted by a recruiter for a candidate with no account
    job_id: uuid.UUID
    resume_id: uuid.UUID | None
    status: ApplicationStatus
    shortlist_stage: ShortlistStage | None = None
    interview_stage: InterviewStage | None = None
    interview_at: datetime | None = None
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
    applicant_email: str | None
    applicant_name: str | None
    # Set only for recruiter-submitted applications (user_id is None).
    submitted_by_email: str | None = None
    resume_filename: str | None = None
    match_score: float | None = None
    # Recruiter-entered, optional. Separate from match_score (the AI score).
    # Only on this recruiter-facing schema, never on ApplicationRead /
    # ApplicationWithJob, which candidates receive.
    manual_score: float | None = None
    match_status: str = "pending"
    match_details: dict | None = None
    match_error: str | None = None


# Cap per request: each row is a few queries plus a queued scoring task.
MAX_BULK_APPLY = 200


class BulkApplyRequest(BaseModel):
    resume_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_BULK_APPLY)


class BulkApplyResult(BaseModel):
    """One entry per resume / file submitted. A batch can partially fail,
    so each gets its own outcome (same idea as ResumeBulkUploadResult)."""
    original_filename: str
    success: bool
    resume_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    error: str | None = None
