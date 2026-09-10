import logging
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session
from app.core.audit import record_audit, snapshot
from app.core.deps import get_current_user, require_recruiter_or_admin
from app.core.text_extract import extract_text_from_upload
from app.core.llm_extract import ExtractionError, extract_job_requirements
from app.db.session import get_db
from app.models.job import Job, JobExtractionStatus, JobStatus, EmploymentType, SeniorityLevel, RemoteType
from app.models.user import User, UserRole
from app.schemas.job import JobCreate, JobRead, JobUpdate
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("", response_model=list[JobRead])
def list_jobs(
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    location: str | None = Query(default=None),
    employment_type: EmploymentType | None = Query(default=None),
    seniority: SeniorityLevel | None = Query(default=None),
    remote_type: RemoteType | None = Query(default=None),
    department: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Job)

    if current_user.role == UserRole.USER:
        query = query.filter(Job.status == JobStatus.PUBLISHED)
    elif status_filter is not None:
        query = query.filter(Job.status == status_filter)

    if location:
        query = query.filter(Job.location.ilike(f"%{location}%"))
    if employment_type:
        query = query.filter(Job.employment_type == employment_type)
    if seniority:
        query = query.filter(Job.seniority == seniority)
    if remote_type:
        query = query.filter(Job.remote_type == remote_type)
    if department:
        query = query.filter(Job.department.ilike(f"%{department}%"))

    return query.order_by(Job.created_at.desc()).offset(offset).limit(limit).all()

@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, db: Session = Depends(get_db), current_user: User = Depends(require_recruiter_or_admin)):
    # payload.model_dump() covers every JobCreate field (location, employment_type,
    # department, seniority, remote_type, salary range, required_skills,
    # experience/education requirements, closes_at) — every one of these has a
    # matching column on Job, so this replaces the old title/description-only
    # construction that silently dropped the rest of the form on creation.
    job = Job(**payload.model_dump(), created_by=current_user)
    db.add(job)
    db.flush()  # assigns job.id before we snapshot it for the audit row
    record_audit(
        db, actor=current_user, action="create", resource_type="job",
        resource_id=job.id, after=snapshot(job, "job"),
    )
    db.commit()
    db.refresh(job)
    return job

def _get_visible_job(job_id: uuid.UUID, db: Session, current_user: User) -> Job:
    """Read-access lookup: USERs can see any PUBLISHED job; recruiters/
    admins/superuser can see any job at all (full view, no ownership restriction)."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if current_user.role == UserRole.USER and job.status != JobStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job

def _get_owned_job(job_id: uuid.UUID, db: Session, current_user: User) -> Job:
    """Write-access lookup: admins/superuser can mutate any job; recruiters
    only their own. Same 404-for-both trick as before to avoid leaking
    existence of jobs the caller doesn't own."""
    job = db.get(Job, job_id)
    is_privileged = current_user.role in (UserRole.ADMIN, UserRole.SUPERUSER)
    if job is None or (not is_privileged and job.created_by_id != current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job

@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _get_visible_job(job_id, db, current_user)

_ALLOWED_STATUS_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.DRAFT: {JobStatus.PUBLISHED, JobStatus.CLOSED},
    JobStatus.PUBLISHED: {JobStatus.CLOSED},
    JobStatus.CLOSED: set(),  # closed is terminal — reopen by creating a new posting
}

@router.patch("/{job_id}", response_model=JobRead)
def update_job(job_id: uuid.UUID, payload: JobUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_recruiter_or_admin)):
    job = _get_owned_job(job_id, db, current_user)
    before = snapshot(job, "job")
    updates = payload.model_dump(exclude_unset=True)

    new_status = updates.get("status")
    if new_status is not None and new_status != job.status:
        allowed = _ALLOWED_STATUS_TRANSITIONS.get(job.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot move a job from '{job.status.value}' to '{new_status.value}'.",
            )
        if new_status == JobStatus.PUBLISHED:
            title = updates.get("title", job.title)
            description = updates.get("description", job.description)
            if not title or not description:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A job needs both a title and a description before it can be published.",
                )
            if not job.jd_raw_text:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A job needs a job description file uploaded before it can be published.",
                )

    if updates.get("status") == JobStatus.PUBLISHED and job.published_at is None:
        job.published_at = datetime.now(timezone.utc)
    for field, value in updates.items():
        setattr(job, field, value)
    if updates:
        record_audit(
            db, actor=current_user, action="update", resource_type="job",
            resource_id=job.id, before=before, after=snapshot(job, "job"),
        )
    db.commit()
    db.refresh(job)
    return job

@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(require_recruiter_or_admin)):
    job = _get_owned_job(job_id, db, current_user)
    record_audit(
        db, actor=current_user, action="delete", resource_type="job",
        resource_id=job.id, before=snapshot(job, "job"),
    )
    db.delete(job)
    db.commit()

_ALLOWED_JD_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
}
_MAX_JD_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

@router.post("/{job_id}/jd", response_model=JobRead)
async def upload_jd(job_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(require_recruiter_or_admin)):
    job = _get_owned_job(job_id, db, current_user)

    if file.content_type not in _ALLOWED_JD_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Job description must be a PDF or DOCX file.",
        )

    # Read once to enforce a size cap before handing the bytes to the parser —
    # extract_text_from_upload has no size limit of its own, so an
    # unbounded file was a straightforward DoS vector.
    contents = await file.read()
    if len(contents) > _MAX_JD_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Job description file must be under 10 MB.",
        )
    await file.seek(0)

    had_jd_before = job.jd_raw_text is not None
    job.jd_raw_text = await extract_text_from_upload(file)

    # Structured extraction (Phase 4) — synchronous for now, same pattern
    # as resume extraction. Failure here never blocks the JD upload
    # itself: jd_raw_text is already saved above regardless of outcome.
    try:
        requirements = extract_job_requirements(job.jd_raw_text)
    except ExtractionError as exc:
        job.extraction_status = JobExtractionStatus.FAILED
        job.extraction_error = str(exc)
    except Exception as exc:  # Ollama unreachable, model not pulled, etc.
        logger.warning("JD extraction failed for job %s: %s", job.id, exc)
        job.extraction_status = JobExtractionStatus.FAILED
        job.extraction_error = f"Extraction failed: {exc}"
    else:
        job.extracted_required_skills = requirements.required_skills
        job.extracted_min_experience_years = requirements.min_experience_years
        job.extracted_max_experience_years = requirements.max_experience_years
        job.extracted_education_requirement = requirements.education_requirement
        job.extracted_profile = requirements.model_dump()
        job.extraction_status = JobExtractionStatus.DONE
        job.extracted_at = datetime.now(timezone.utc)

    # jd_raw_text itself is excluded from snapshots (see _SNAPSHOT_EXCLUDE) —
    # it can be large and the file content isn't useful to diff in an audit
    # trail. What matters here is recording that an upload happened.
    record_audit(
        db, actor=current_user, action="update", resource_type="job",
        resource_id=job.id,
        before={"jd_uploaded": had_jd_before},
        after={"jd_uploaded": True, "jd_filename": file.filename},
    )
    db.commit()
    db.refresh(job)
    return job