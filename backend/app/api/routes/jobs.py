import logging
import uuid
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.audit import record_audit, snapshot
from app.core.deps import (
    get_current_user,
    require_recruiter_or_admin,
)
from app.core.jd_skills_extraction_tasks import run_jd_skills_extraction_task
from app.core.resume_storage import build_blob_name, upload_resume_blob
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
from app.models.user import User, UserRole
from app.schemas.job import JobCreate, JobRead, JobUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


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
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Job)

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

    return (
        query.order_by(Job.created_at.desc())
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
    job = Job(
        **payload.model_dump(),
        created_by=current_user,
    )

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

    is_privileged = current_user.role in (
        UserRole.ADMIN,
        UserRole.SUPERUSER,
    )

    if (
        job is None
        or (
            not is_privileged
            and job.created_by_id != current_user.id
        )
    ):
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
    JobStatus.CLOSED: set(),
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

    contents = await file.read()

    if len(contents) > _MAX_JD_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Job description file must be under 10 MB.",
        )

    await file.seek(0)

    had_jd_before = job.jd_raw_text is not None

    # New upload supersedes any previous skills-extraction result.
    job.skills_result = None
    job.skills_section_heading = None
    job.skills_extraction_status = JobExtractionStatus.PENDING
    job.skills_extraction_error = None
    job.skills_extracted_at = None

    job.jd_raw_text = await extract_text_from_upload(file)

    # Store the file itself, mirroring resumes.py's use of
    # resume_storage.py -- these wrappers were built generic from the
    # start (see azure_blob.py / local_disk.py docstrings), so no
    # JD-specific storage module is needed here.
    blob_name = build_blob_name(job.created_by_id, file.filename)

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
    run_jd_skills_extraction_task.delay(str(job.id))

    return job