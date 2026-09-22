import logging
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload
from app.core.audit import record_audit, snapshot
from app.core.config import settings
from app.core.deps import get_current_user, require_recruiter_or_admin
from app.core.extraction_tasks import run_extraction_task
from app.core.resume_storage import build_blob_name, delete_resume_blob, download_resume_blob, get_resume_download_url, upload_resume_blob
from app.core.skills_extraction_tasks import run_skills_extraction_task
from app.db.session import get_db
from app.models.resume import Resume, ResumeExtractionStatus, ResumeStatus
from app.models.user import User, UserRole
from app.schemas.resume import ResumeBulkUploadResult, ResumeRead, ResumeReadWithUrl

logger = logging.getLogger(__name__)

router = APIRouter()

_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_MAX_RESUME_UPLOAD_BYTES = 10 * 1024 * 1024


def _validate_upload(content_type: str, size: int) -> None:
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Resume must be a PDF or DOCX file.",
        )
    if size > _MAX_RESUME_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Resume file must be under 10 MB.",
        )


def _store_one(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    owner_id: uuid.UUID | None,
    uploaded_by: User,
    db: Session,
) -> Resume:
    """No longer runs extraction inline — that moved to
    run_extraction_task, dispatched by the route handlers below, after
    their own commit succeeds. A resume row created here always starts
    at its default extraction_status (PENDING)."""
    blob_name = build_blob_name(owner_id, filename)
    try:
        blob_path = upload_resume_blob(file_bytes, blob_name, content_type)
        upload_status = ResumeStatus.UPLOADED
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to store '{filename}': {exc}",
        )

    resume = Resume(
        owner_id=owner_id,
        uploaded_by_id=uploaded_by.id,
        original_filename=filename,
        content_type=content_type,
        size_bytes=len(file_bytes),
        blob_path=blob_path,
        status=upload_status,
    )
    db.add(resume)
    db.flush()
    record_audit(
        db, actor=uploaded_by, action="create", resource_type="resume",
        resource_id=resume.id, after=snapshot(resume, "resume"),
    )
    return resume


@router.post("", response_model=ResumeRead, status_code=status.HTTP_201_CREATED)
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
    as the file is safely stored, with extraction_status still PENDING.
    The frontend should poll GET /resumes/{id} to see it flip to
    DONE/FAILED once the Celery worker gets to it.
    """
    contents = await file.read()
    _validate_upload(file.content_type, len(contents))

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

    resume = _store_one(contents, file.filename, file.content_type, current_user.id, current_user, db)
    db.commit()
    db.refresh(resume)

    if resume.status == ResumeStatus.UPLOADED:
        run_extraction_task.delay(str(resume.id))

    return resume


@router.post("/bulk", response_model=list[ResumeBulkUploadResult])
async def upload_resumes_bulk(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    results: list[ResumeBulkUploadResult] = []
    stored_ids: list[uuid.UUID] = []
    for file in files:
        contents = await file.read()
        try:
            with db.begin_nested():
                _validate_upload(file.content_type, len(contents))
                resume = _store_one(contents, file.filename, file.content_type, None, current_user, db)
                db.flush()
            results.append(ResumeBulkUploadResult(
                original_filename=file.filename, success=True,
                resume=ResumeRead.model_validate(resume),
            ))
            stored_ids.append(resume.id)
        except HTTPException as exc:
            results.append(ResumeBulkUploadResult(
                original_filename=file.filename, success=False, error=exc.detail,
            ))

    db.commit()
    for resume_id in stored_ids:
        run_extraction_task.delay(str(resume_id))
    return results


def _get_visible_resume(resume_id: uuid.UUID, db: Session, current_user: User) -> Resume:
    resume = db.get(Resume, resume_id)
    is_privileged = current_user.role in (UserRole.RECRUITER, UserRole.ADMIN, UserRole.SUPERUSER)
    if resume is None or (not is_privileged and resume.owner_id != current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    return resume


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
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Resume).options(joinedload(Resume.owner), joinedload(Resume.uploaded_by))
    if current_user.role == UserRole.USER:
        query = query.filter(Resume.owner_id == current_user.id)
    if not include_archived:
        query = query.filter(Resume.is_archived.is_(False))
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
    return Response(content=contents, media_type=resume.content_type, headers={"Content-Disposition": f'inline; filename="{resume.original_filename}"'})


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


@router.post("/{resume_id}/extract-skills", response_model=ResumeRead)
def trigger_skills_extraction(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Separately-triggerable skills-only extraction -- NOT fired
    automatically on upload and NOT part of run_extraction_task's
    full-profile pass. Re-runnable on its own (e.g. after a prompt or
    section-locator change) without redoing full-profile extraction.

    Queues app.core.skills_extraction_tasks.run_skills_extraction_task
    and returns immediately with skills_extraction_status flipped to
    PENDING; poll GET /resumes/{id} for it to reach DONE/FAILED.
    """
    resume = _get_manageable_resume(resume_id, db, current_user)

    resume.skills_extraction_status = ResumeExtractionStatus.PENDING
    resume.skills_extraction_error = None
    db.commit()
    db.refresh(resume)

    run_skills_extraction_task.delay(str(resume.id))

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