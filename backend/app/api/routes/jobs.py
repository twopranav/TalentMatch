import logging
import uuid
from datetime import datetime, timezone

from fastapi import Response
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.audit import record_audit, snapshot
from app.core.deps import (
    rate_limit_user,
    get_current_user,
    require_recruiter_or_admin,
)
from app.core.jd_skills_extraction_tasks import run_jd_skills_extraction_task
from app.core.resume_storage import build_blob_name, upload_resume_blob
from app.core.upload_safety import check_magic, read_capped
from app.core.text_extract import extract_text_from_upload
from app.db.session import get_db
from app.models.job import (
    EmploymentType,
    Job,
    JobExtractionStatus,
    JobStatus,
    RemoteType,
    SeniorityLevel,
)
from app.core.access import apply_status_change, can_read_job, can_write_job, job_read_clause
from app.models.user import User, UserRole
from app.schemas.job import JobCreate, JobRead, JobSkillsUpdate, JobUpdate
from app.core.dispatch import dispatch_extraction
from app.core.matching_tasks import safe_dispatch_for_job
from app.core.rate_limit import enforce
from app.models.application import Application, ApplicationStatus, ShortlistStage
from app.schemas.application import MAX_BULK_APPLY

logger = logging.getLogger(__name__)

router = APIRouter()


def _like_escape(text: str) -> str:
    """Escape LIKE wildcards so a search for '100%' or 'a_b' is literal."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("", response_model=list[JobRead])
def list_jobs(
    status_filter: JobStatus | None = Query(
        default=None,
        alias="status",
    ),
    location: str | None = Query(default=None),
    employment_type: EmploymentType | None = Query(default=None),
    seniority: SeniorityLevel | None = Query(default=None),
    remote_type: RemoteType | None = Query(default=None),
    department: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    response: Response = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Job)

    if current_user.role != UserRole.USER:
        query = query.filter(job_read_clause(current_user))

    if current_user.role == UserRole.USER:
        query = query.filter(
            Job.status == JobStatus.PUBLISHED
        )
    elif status_filter is not None:
        query = query.filter(
            Job.status == status_filter
        )

    if location:
        query = query.filter(
            Job.location.ilike(f"%{location}%")
        )

    if employment_type:
        query = query.filter(
            Job.employment_type == employment_type
        )

    if seniority:
        query = query.filter(
            Job.seniority == seniority
        )

    if remote_type:
        query = query.filter(
            Job.remote_type == remote_type
        )

    if department:
        query = query.filter(
            Job.department.ilike(f"%{department}%")
        )

    if q and q.strip():
        pattern = f"%{_like_escape(q.strip())}%"
        query = query.filter(
            or_(
                Job.title.ilike(pattern, escape="\\"),
                Job.department.ilike(pattern, escape="\\"),
                Job.location.ilike(pattern, escape="\\"),
                Job.description.ilike(pattern, escape="\\"),
            )
        )

    total = query.order_by(None).count()
    if response is not None:
        response.headers["X-Total-Count"] = str(total)

    return (
        query.order_by(Job.created_at.desc(), Job.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.post(
    "",
    response_model=JobRead,
    status_code=status.HTTP_201_CREATED,
)
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    data = payload.model_dump()
    requested = data.pop("sub_company", None)
    if current_user.role == UserRole.SUPERUSER:
        sub_company = requested
        if sub_company is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a sub company for this job.")
    else:
        sub_company = current_user.sub_company
        if sub_company is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your account has no sub company yet. Ask the superuser to assign one.")
    job = Job(**data, sub_company=sub_company, created_by=current_user)

    db.add(job)
    db.flush()

    record_audit(
        db,
        actor=current_user,
        action="create",
        resource_type="job",
        resource_id=job.id,
        after=snapshot(job, "job"),
    )

    db.commit()
    db.refresh(job)

    return job


def _get_visible_job(
    job_id: uuid.UUID,
    db: Session,
    current_user: User,
) -> Job:
    """
    USERs can see published jobs.

    Recruiters/admins/superusers can see every job.
    """
    job = db.get(Job, job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    if (
        current_user.role == UserRole.USER
        and job.status != JobStatus.PUBLISHED
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    if current_user.role != UserRole.USER and not can_read_job(current_user, job):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return job


def _get_owned_job(
    job_id: uuid.UUID,
    db: Session,
    current_user: User,
) -> Job:
    """
    Admins/superusers can mutate any job.

    Recruiters can mutate only their own jobs.
    """
    job = db.get(Job, job_id)

    if job is None or not can_write_job(current_user, job):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return job


@router.get(
    "/{job_id}",
    response_model=JobRead,
)
def get_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_visible_job(
        job_id,
        db,
        current_user,
    )


_ALLOWED_STATUS_TRANSITIONS: dict[
    JobStatus,
    set[JobStatus],
] = {
    JobStatus.DRAFT: {
        JobStatus.PUBLISHED,
        JobStatus.CLOSED,
    },
    JobStatus.PUBLISHED: {
        JobStatus.CLOSED,
    },
    # A closed job can be reopened. The publish prerequisites (title,
    # description, JD file) are re-checked below, and published_at keeps
    # its original value. Closed -> draft is not allowed.
    JobStatus.CLOSED: {
        JobStatus.PUBLISHED,
    },
}


@router.patch(
    "/{job_id}",
    response_model=JobRead,
)
def update_job(
    job_id: uuid.UUID,
    payload: JobUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    job = _get_owned_job(
        job_id,
        db,
        current_user,
    )

    before = snapshot(job, "job")

    updates = payload.model_dump(
        exclude_unset=True
    )

    new_status = updates.get("status")

    if (
        new_status is not None
        and new_status != job.status
    ):
        allowed = _ALLOWED_STATUS_TRANSITIONS.get(
            job.status,
            set(),
        )

        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot move a job from "
                    f"'{job.status.value}' to "
                    f"'{new_status.value}'."
                ),
            )

        if new_status == JobStatus.PUBLISHED:
            title = updates.get(
                "title",
                job.title,
            )

            description = updates.get(
                "description",
                job.description,
            )

            if not title or not description:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "A job needs both a title and "
                        "a description before it can be published."
                    ),
                )

            if not job.jd_raw_text:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "A job needs a job description file "
                        "uploaded before it can be published."
                    ),
                )

    if (
        updates.get("status") == JobStatus.PUBLISHED
        and job.published_at is None
    ):
        job.published_at = datetime.now(timezone.utc)

    for field, value in updates.items():
        setattr(job, field, value)

    if updates:
        record_audit(
            db,
            actor=current_user,
            action="update",
            resource_type="job",
            resource_id=job.id,
            before=before,
            after=snapshot(job, "job"),
        )

    db.commit()
    db.refresh(job)

    return job


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    job = _get_owned_job(
        job_id,
        db,
        current_user,
    )

    record_audit(
        db,
        actor=current_user,
        action="delete",
        resource_type="job",
        resource_id=job.id,
        before=snapshot(job, "job"),
    )

    db.delete(job)
    db.commit()


_ALLOWED_JD_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_MAX_JD_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post(
    "/{job_id}/jd",
    response_model=JobRead,
    dependencies=[Depends(rate_limit_user("upload", 30, 60))],
)
async def upload_jd(
    job_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    job = _get_owned_job(
        job_id,
        db,
        current_user,
    )

    if file.content_type not in _ALLOWED_JD_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Job description must be a PDF or DOCX file.",
        )

    contents = await read_capped(file, _MAX_JD_UPLOAD_BYTES, "Job description file")
    check_magic(file.content_type, contents)

    await file.seek(0)

    had_jd_before = job.jd_raw_text is not None

    # New upload supersedes any previous skills-extraction result.
    job.skills_result = None
    job.skills_section_heading = None
    job.skills_extraction_status = JobExtractionStatus.PENDING
    job.skills_extraction_error = None
    job.skills_extracted_at = None
    job.skills_extraction_retry_count = 0

    job.jd_raw_text = await extract_text_from_upload(file)

    # Store the file itself, mirroring resumes.py's use of
    # resume_storage.py -- these wrappers were built generic from the
    # start (see azure_blob.py / local_disk.py docstrings), so no
    # JD-specific storage module is needed here.
    blob_name = build_blob_name(job.created_by_id, file.filename, file.content_type)

    try:
        blob_path = await run_in_threadpool(
            upload_resume_blob,
            contents,
            blob_name,
            file.content_type,
        )
    except Exception as exc:
        logger.exception(
            "Failed to store JD file for job %s",
            job.id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not store the job description file. Please try again.",
        ) from exc

    job.blob_path = blob_path
    job.original_filename = file.filename
    job.content_type = file.content_type
    job.size_bytes = len(contents)

    record_audit(
        db,
        actor=current_user,
        action="update",
        resource_type="job",
        resource_id=job.id,
        before={
            "jd_uploaded": had_jd_before,
        },
        after={
            "jd_uploaded": True,
            "jd_filename": file.filename,
            "skills_extraction_status": (
                job.skills_extraction_status.value
            ),
        },
    )

    db.commit()
    db.refresh(job)

    # Dispatched after commit: the Celery task looks the job up by id in
    # its own DB session (see jd_skills_extraction_tasks.py), so the row
    # -- including the blob_path/jd_raw_text just written -- must already
    # be committed before the worker can see it.
    dispatch_extraction(run_jd_skills_extraction_task, job.id)
    
    return job


@router.post(
    "/{job_id}/extract-skills",
    response_model=JobRead,
    dependencies=[Depends(rate_limit_user("extract", 10, 60))],
)
def trigger_jd_skills_extraction(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    """Manual re-run of JD skills extraction (JD upload already triggers
    it automatically) -- e.g. after a locator/prompt/model change, or to
    recover a row the retry sweep gave up on. Mirrors
    POST /resumes/{resume_id}/extract-skills.

    Queues app.core.jd_skills_extraction_tasks.run_jd_skills_extraction_task
    and returns immediately with skills_extraction_status flipped to
    PENDING and the retry counter reset to 0 (so the sweep will retry it
    again if it fails). The previous skills_result is left in place until
    the new run overwrites it. Poll GET /jobs/{job_id} for it to reach
    DONE/FAILED.
    """
    job = _get_owned_job(
        job_id,
        db,
        current_user,
    )

    if not job.blob_path and not (job.jd_raw_text and job.jd_raw_text.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload a job description file before extracting skills.",
        )

    previous_status = job.skills_extraction_status.value

    job.skills_extraction_status = JobExtractionStatus.PENDING
    job.skills_extraction_error = None
    job.skills_extraction_retry_count = 0

    record_audit(
        db,
        actor=current_user,
        action="update",
        resource_type="job",
        resource_id=job.id,
        before={
            "skills_extraction_status": previous_status,
        },
        after={
            "skills_extraction_status": (
                job.skills_extraction_status.value
            ),
            "trigger": "manual_skills_reextract",
        },
    )

    db.commit()
    db.refresh(job)

    # After commit, same reason as upload_jd: the worker reads the row in
    # its own session.
    dispatch_extraction(run_jd_skills_extraction_task, job.id)

    return job


@router.put(
    "/{job_id}/skills",
    response_model=JobRead,
)
def update_job_skills(
    job_id: uuid.UUID,
    payload: JobSkillsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    """Recruiter correction of the LLM-extracted skill list.

    Replaces Job.skills_result with the submitted list. That column is
    exactly what applicant scoring reads (matching_tasks.score_application_task),
    so removed skills stop counting and added ones start counting.

    - Rejected with 409 while extraction is queued/running, because the
      worker would overwrite the edit moments later.
    - If extraction FAILED, saving a list here rescues the job: it is
      marked DONE so applicants can be scored against the manual list.
    - Existing applicants are re-queued for scoring so the ranking never
      mixes scores computed against two different skill lists.
    - A later re-extraction (new JD upload or POST /extract-skills)
      replaces manual edits with fresh LLM output.
    """
    job = _get_owned_job(
        job_id,
        db,
        current_user,
    )

    has_jd = bool(job.blob_path or (job.jd_raw_text and job.jd_raw_text.strip()))
    extraction_in_flight = (
        job.skills_extraction_status == JobExtractionStatus.PROCESSING
        or (
            job.skills_extraction_status == JobExtractionStatus.PENDING
            and has_jd
        )
    )
    if extraction_in_flight:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Skills are still being extracted from the job description. "
                "Try again once extraction has finished."
            ),
        )

    before = {
        "skills_result": job.skills_result,
        "skills_extraction_status": job.skills_extraction_status.value,
    }

    job.skills_result = payload.skills
    if job.skills_extraction_status != JobExtractionStatus.DONE:
        job.skills_extraction_status = JobExtractionStatus.DONE
        job.skills_extraction_error = None

    record_audit(
        db,
        actor=current_user,
        action="update",
        resource_type="job",
        resource_id=job.id,
        before=before,
        after={
            "skills_result": job.skills_result,
            "skills_extraction_status": job.skills_extraction_status.value,
            "trigger": "manual_skills_edit",
        },
    )

    db.commit()
    db.refresh(job)

    # After commit (the worker reads in its own session). Best-effort; the
    # sweep only covers 'pending' rows, so a lost message here means an
    # applicant keeps their old score until the recruiter hits /rescore.
    safe_dispatch_for_job(db, job.id)

    return job


class BulkApplicationStatusPayload(BaseModel):
    application_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_BULK_APPLY)
    status: ApplicationStatus


@router.post("/{job_id}/applications/bulk-status")
def bulk_update_application_status(
    job_id: uuid.UUID,
    payload: BulkApplicationStatusPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    """Move many applications of ONE job to a new status. Recruiters can only
    act on their own jobs (others 404); ids that don't belong to the job get a
    per-item failure instead of failing the whole batch."""
    enforce(f"bulk-status:user:{current_user.id}", 10, 60)
    job = _get_owned_job(job_id, db, current_user)
    ids = list(dict.fromkeys(payload.application_ids))  # de-dupe, keep order
    rows = db.query(Application).filter(Application.job_id == job.id, Application.id.in_(ids)).all()
    by_id = {row.id: row for row in rows}
    results = []
    for app_id in ids:
        application = by_id.get(app_id)
        if application is None:
            results.append({"application_id": str(app_id), "success": False, "detail": "Application not found for this job."})
            continue
        if application.status == payload.status:
            results.append({"application_id": str(app_id), "success": True, "status": payload.status.value, "changed": False})
            continue
        before = snapshot(application, "application")
        apply_status_change(application, payload.status)
        record_audit(
            db, actor=current_user, action="update", resource_type="application",
            resource_id=application.id, before=before, after=snapshot(application, "application"),
        )
        results.append({"application_id": str(app_id), "success": True, "status": payload.status.value, "changed": True})
    db.commit()
    return {
        "job_id": str(job.id),
        "results": results,
        "requested": len(ids),
        "updated": sum(1 for item in results if item["success"]),
    }
