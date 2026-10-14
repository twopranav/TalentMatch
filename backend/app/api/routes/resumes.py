import logging
import uuid
from dataclasses import dataclass
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload
from app.core.audit import record_audit, snapshot
from app.core.config import settings
from app.core.deps import get_current_user, rate_limit_user, require_recruiter_or_admin
from app.core.upload_safety import check_magic, content_disposition, read_capped
from app.core.resume_storage import build_blob_name, delete_resume_blob, download_resume_blob, get_resume_download_url, upload_resume_blob
from app.core.skills_extraction_tasks import run_skills_extraction_task
from app.db.session import get_db
from app.models.resume import Resume, ResumeExtractionStatus, ResumeStatus
from app.models.user import User, UserRole
from app.models.application import Application
from app.models.job import Job
from app.schemas.resume import ResumeBulkUploadResult, ResumeRead, ResumeReadWithUrl
from app.core.dispatch import dispatch_extraction
from app.core.threaded import run_in_threads

logger = logging.getLogger(__name__)

router = APIRouter()

_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_MAX_RESUME_UPLOAD_BYTES = 10 * 1024 * 1024


MAX_RESUMES_BULK = 50


def _validate_upload(content_type: str, contents: bytes) -> None:
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Resume must be a PDF or DOCX file.",
        )
    if len(contents) > _MAX_RESUME_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Resume file must be under 10 MB.",
        )
    check_magic(content_type, contents)


def _make_resume_row(
    blob_path: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    owner_id: uuid.UUID | None,
    uploaded_by: User,
    db: Session,
) -> Resume:
    """Creates the Resume row (and its audit entry) for a blob that is
    already stored. Flushes, so resume.id is set; the caller commits."""
    resume = Resume(
        owner_id=owner_id,
        uploaded_by_id=uploaded_by.id,
        original_filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        blob_path=blob_path,
        status=ResumeStatus.UPLOADED,
    )
    db.add(resume)
    db.flush()
    record_audit(
        db, actor=uploaded_by, action="create", resource_type="resume",
        resource_id=resume.id, after=snapshot(resume, "resume"),
    )
    return resume


def _store_failed(filename: str) -> str:
    return f"Failed to store '{filename}'."


def _store_one(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    owner_id: uuid.UUID | None,
    uploaded_by: User,
    db: Session,
) -> Resume:
    """Does not run extraction inline — the route handlers below dispatch
    run_skills_extraction_task after their own commit succeeds. A resume
    row created here always starts at its default
    skills_extraction_status (PENDING)."""
    blob_path = _upload_blob(file_bytes, filename, content_type, owner_id)
    return _make_resume_row(blob_path, filename, content_type, len(file_bytes), owner_id, uploaded_by, db)


def _upload_blob(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    owner_id: uuid.UUID | None,
) -> str:
    """The blocking storage write only (no DB). Async routes run this in a
    worker thread via run_in_threadpool so a slow storage call can't freeze
    the event loop; keeping the DB session out of it means a Session is
    never touched from two threads."""
    blob_name = build_blob_name(owner_id, filename, content_type)
    try:
        return upload_resume_blob(file_bytes, blob_name, content_type)
    except Exception:
        # The storage error can carry the container URL, so it goes to the
        # log, not to the client.
        logger.exception("Storing '%s' failed", filename)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=_store_failed(filename))


def _discard_blob(blob_path: str | None) -> None:
    """Best-effort cleanup of a blob whose DB row never made it."""
    if not blob_path:
        return
    try:
        delete_resume_blob(blob_path)
    except Exception:
        logger.warning("Could not delete orphaned blob %s", blob_path, exc_info=True)


@dataclass
class StagedUpload:
    """One file of a bulk request after read + validate + store.
    Exactly one of blob_path / error is set."""
    file: UploadFile
    size: int = 0
    blob_path: str | None = None
    error: str | None = None


async def stage_uploads(files: list[UploadFile]) -> list[StagedUpload]:
    """Reads, validates and stores every file for a bulk request, without
    touching the database. Never raises for a bad file: each result carries
    its own error, in the same order as `files`.

    Two things keep this safe at 50-200 files:
    - Files are processed BULK_CHUNK_SIZE at a time, so only a chunk's bytes
      are held in memory (not the whole request).
    - Within a chunk, the blocking storage uploads run in worker threads
      BULK_UPLOAD_CONCURRENCY at a time. That is both faster than one by one
      and keeps the event loop free, so other requests aren't stalled.
    """
    staged = [StagedUpload(file=f) for f in files]
    step = max(1, settings.BULK_CHUNK_SIZE)

    for start in range(0, len(staged), step):
        to_store: list[tuple[StagedUpload, bytes]] = []
        for item in staged[start:start + step]:
            try:
                contents = await read_capped(item.file, _MAX_RESUME_UPLOAD_BYTES, "Resume file")
                _validate_upload(item.file.content_type, contents)
            except HTTPException as exc:
                item.error = exc.detail
                continue
            item.size = len(contents)
            to_store.append((item, contents))

        results = await run_in_threads(
            upload_resume_blob,
            [
                (contents, build_blob_name(None, item.file.filename, item.file.content_type), item.file.content_type)
                for item, contents in to_store
            ],
            settings.BULK_UPLOAD_CONCURRENCY,
        )
        for (item, _), result in zip(to_store, results):
            if isinstance(result, BaseException):
                logger.error("Storing '%s' failed", item.file.filename, exc_info=result)
                item.error = _store_failed(item.file.filename)
            else:
                item.blob_path = result
        del to_store, results  # drop the chunk's bytes before the next one

    return staged


@router.post(
    "",
    response_model=ResumeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_user("upload", 30, 60))],
)
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Self-upload: the caller becomes the resume's owner. A candidate has
    at most one *active* resume — a repeat upload archives the previous
    one rather than accumulating unlimited active resumes or destroying
    it outright.

    Extraction is queued, not run inline: the response comes back as soon
    as the file is safely stored, with skills_extraction_status still
    PENDING. The frontend should poll GET /resumes/{id} to see it flip to
    DONE/FAILED once the Celery worker gets to it. Applying to a job later
    only checks that status (see applications._require_ready_resume); it
    never triggers extraction itself.
    """
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Resume must be a PDF or DOCX file.",
        )
    contents = await read_capped(file, _MAX_RESUME_UPLOAD_BYTES, "Resume file")
    _validate_upload(file.content_type, contents)

    existing = (
        db.query(Resume)
        .filter(Resume.owner_id == current_user.id, Resume.is_archived.is_(False))
        .first()
    )
    if existing is not None:
        # Archived, not deleted: an Application row created against this
        # resume (Application.resume_id -> Resume.id, ON DELETE SET NULL)
        # must keep pointing at exactly what the candidate submitted at
        # apply-time, forever — hard-deleting here would null out that
        # link on every past application the instant the candidate
        # replaces their resume. Archiving keeps the row (and its blob)
        # alive under the same id, just excluded from
        # "current active resume" queries (is_archived.is_(False)),
        # which is what both this replace-check and
        # _require_ready_resume filter on. A NEW application always
        # picks up the new active resume; nothing about a past one
        # changes.
        before = snapshot(existing, "resume")
        existing.is_archived = True
        record_audit(
            db, actor=current_user, action="update", resource_type="resume",
            resource_id=existing.id, before=before, after=snapshot(existing, "resume"),
        )
        db.flush()

    blob_path = await run_in_threadpool(
        _upload_blob, contents, file.filename, file.content_type, current_user.id
    )
    resume = _make_resume_row(
        blob_path, file.filename, file.content_type, len(contents), current_user.id, current_user, db
    )
    db.commit()
    db.refresh(resume)

    if resume.status == ResumeStatus.UPLOADED:
        dispatch_extraction(run_skills_extraction_task, resume.id)

    return resume


@router.post(
    "/bulk",
    response_model=list[ResumeBulkUploadResult],
    dependencies=[Depends(rate_limit_user("upload", 30, 60))],
)
async def upload_resumes_bulk(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    if len(files) > MAX_RESUMES_BULK:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Upload at most {MAX_RESUMES_BULK} files at a time.",
        )
    # Phase 1: read, validate and store every blob (in parallel, off the
    # event loop). Phase 2: one DB row per stored file, each in its own
    # savepoint so a bad row doesn't sink the others.
    staged = await stage_uploads(files)

    results: list[ResumeBulkUploadResult] = []
    stored_ids: list[uuid.UUID] = []
    stored_blobs: list[str] = []
    for item in staged:
        filename = item.file.filename
        if item.error is not None:
            results.append(ResumeBulkUploadResult(original_filename=filename, success=False, error=item.error))
            continue
        try:
            with db.begin_nested():
                resume = _make_resume_row(
                    item.blob_path, filename, item.file.content_type, item.size, None, current_user, db,
                )
            results.append(ResumeBulkUploadResult(
                original_filename=filename, success=True,
                resume=ResumeRead.model_validate(resume),
            ))
            stored_ids.append(resume.id)
            stored_blobs.append(item.blob_path)
        except Exception:
            logger.exception("Saving resume row for '%s' failed", filename)
            _discard_blob(item.blob_path)
            results.append(ResumeBulkUploadResult(
                original_filename=filename, success=False, error="Could not save this file.",
            ))

    try:
        db.commit()
    except Exception:
        for blob_path in stored_blobs:
            _discard_blob(blob_path)
        raise
    for resume_id in stored_ids:
        dispatch_extraction(run_skills_extraction_task, resume_id)
    return results


def _applied_to_recruiters_job(resume_id: uuid.UUID, db: Session, recruiter_id: uuid.UUID) -> bool:
    """True if this resume is attached to an application on a job the
    recruiter created. Lets a recruiter open the resumes of their own
    applicants (candidate self-uploads included) without being able to
    browse the rest of the library."""
    return (
        db.query(Application.id)
        .join(Job, Job.id == Application.job_id)
        .filter(Application.resume_id == resume_id, Job.created_by_id == recruiter_id)
        .first()
        is not None
    )


def _get_visible_resume(resume_id: uuid.UUID, db: Session, current_user: User) -> Resume:
    resume = db.get(Resume, resume_id)
    if resume is not None:
        if current_user.role in (UserRole.ADMIN, UserRole.SUPERUSER):
            return resume
        if current_user.role == UserRole.RECRUITER:
            if resume.uploaded_by_id == current_user.id or _applied_to_recruiters_job(resume.id, db, current_user.id):
                return resume
        elif resume.owner_id == current_user.id:
            return resume
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")


def _get_manageable_resume(resume_id: uuid.UUID, db: Session, current_user: User) -> Resume:
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    is_admin = current_user.role in (UserRole.ADMIN, UserRole.SUPERUSER)
    is_owner = resume.owner_id == current_user.id
    is_uploader = resume.uploaded_by_id == current_user.id
    if not (is_admin or is_owner or is_uploader):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    return resume


def _to_read(resume: Resume) -> ResumeRead:
    return ResumeRead(
        **ResumeRead.model_validate(resume).model_dump(exclude={"owner_email", "uploaded_by_email"}),
        owner_email=resume.owner.email if resume.owner else None,
        uploaded_by_email=resume.uploaded_by.email if resume.uploaded_by else None,
    )


@router.get("", response_model=list[ResumeRead])
def list_resumes(
    include_archived: bool = False,
    q: str | None = Query(default=None, max_length=200),
    response: Response = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Resume).options(joinedload(Resume.owner), joinedload(Resume.uploaded_by))
    if current_user.role == UserRole.USER:
        query = query.filter(Resume.owner_id == current_user.id)
    elif current_user.role == UserRole.RECRUITER:
        # A recruiter's library is what they uploaded themselves. Admins and
        # superusers see everything.
        query = query.filter(Resume.uploaded_by_id == current_user.id)    
    if not include_archived:
        query = query.filter(Resume.is_archived.is_(False))
    if q and q.strip():
        term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{term}%"
        query = query.filter(Resume.original_filename.ilike(pattern, escape="\\") | Resume.candidate_name.ilike(pattern, escape="\\") | Resume.candidate_email.ilike(pattern, escape="\\"))
    total = query.order_by(None).count()
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
    resumes = query.order_by(Resume.created_at.desc()).offset(offset).limit(limit).all()
    return [_to_read(r) for r in resumes]


@router.get("/{resume_id}", response_model=ResumeReadWithUrl)
def get_resume(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = _get_visible_resume(resume_id, db, current_user)
    if settings.STORAGE_BACKEND == "azure":
        download_url = get_resume_download_url(resume.blob_path)
    else:
        download_url = f"/api/resumes/{resume.id}/file"
    return ResumeReadWithUrl(
        **_to_read(resume).model_dump(),
        download_url=download_url,
    )


@router.get("/{resume_id}/file")
def download_resume_file(resume_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Proxies bytes through this API for BOTH storage backends now,
    instead of redirecting the browser straight to Azure — a direct
    redirect needs storage-account CORS configured (it wasn't), which
    silently broke ResumePreview.jsx's blob fetch for every resume on
    Azure."""
    resume = _get_visible_resume(resume_id, db, current_user)
    try:
        contents = download_resume_blob(resume.blob_path)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume file is missing from storage.")
    return Response(
        content=contents,
        media_type=resume.content_type,
        headers={
            "Content-Disposition": content_disposition(resume.original_filename),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch("/{resume_id}/archive", response_model=ResumeRead)
def set_resume_archived(
    resume_id: uuid.UUID,
    archived: bool,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = _get_manageable_resume(resume_id, db, current_user)
    before = snapshot(resume, "resume")
    resume.is_archived = archived
    record_audit(
        db, actor=current_user, action="update", resource_type="resume",
        resource_id=resume.id, before=before, after=snapshot(resume, "resume"),
    )
    db.commit()
    db.refresh(resume)
    return resume


@router.post(
    "/{resume_id}/extract-skills",
    response_model=ResumeRead,
    dependencies=[Depends(rate_limit_user("extract", 10, 60))],
)
def trigger_skills_extraction(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manual re-run of skills extraction (upload already triggers it
    automatically) -- e.g. after a prompt or section-locator change.

    Queues app.core.skills_extraction_tasks.run_skills_extraction_task
    and returns immediately with skills_extraction_status flipped to
    PENDING; poll GET /resumes/{id} for it to reach DONE/FAILED.
    """
    resume = _get_manageable_resume(resume_id, db, current_user)

    resume.skills_extraction_status = ResumeExtractionStatus.PENDING
    resume.skills_extraction_error = None
    resume.skills_extraction_retry_count = 0
    db.commit()
    db.refresh(resume)

    dispatch_extraction(run_skills_extraction_task, resume.id)

    return _to_read(resume)


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(resume_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    resume = _get_manageable_resume(resume_id, db, current_user)
    delete_resume_blob(resume.blob_path)
    record_audit(
        db, actor=current_user, action="delete", resource_type="resume",
        resource_id=resume.id, before=snapshot(resume, "resume"),
    )
    db.delete(resume)
    db.commit()