import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session, joinedload
from app.core.audit import record_audit, snapshot
from app.core.config import settings
from app.core.deps import get_current_user, require_recruiter_or_admin
from app.core.resume_storage import build_blob_name, delete_resume_blob, get_resume_download_url, upload_resume_blob
from app.core.text_extract import EmptyExtractionError, UnsupportedFileTypeError, extract_text_from_bytes
from app.core.llm_extract import ExtractionError, extract_candidate_profile
from app.db.session import get_db
from app.models.resume import Resume, ResumeExtractionStatus, ResumeStatus
from app.models.user import User, UserRole
from app.schemas.resume import ResumeBulkUploadResult, ResumeRead, ResumeReadWithUrl

logger = logging.getLogger(__name__)

router = APIRouter()

_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
}
_MAX_RESUME_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB, same cap as JD upload


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


def _run_extraction(resume: Resume, file_bytes: bytes, filename: str, is_sourced: bool) -> None:
    """Runs the Phase 4 extraction pipeline against the bytes just
    uploaded and mutates `resume` in place. Synchronous for now, matching
    how JD text extraction already works on upload — this is the piece to
    move behind Celery later without changing what it does.

    Never raises: a failed/empty extraction marks the row FAILED with a
    reason instead of failing the upload itself, since the file is safely
    stored either way and this is retriable independently later.
    """
    try:
        text = extract_text_from_bytes(file_bytes, filename)
        profile = extract_candidate_profile(text)
    except (UnsupportedFileTypeError, EmptyExtractionError, ExtractionError) as exc:
        resume.extraction_status = ResumeExtractionStatus.FAILED
        resume.extraction_error = str(exc)
        return
    except Exception as exc:  # Ollama unreachable, model not pulled, etc.
        logger.warning("Resume extraction failed for %s: %s", filename, exc)
        resume.extraction_status = ResumeExtractionStatus.FAILED
        resume.extraction_error = f"Extraction failed: {exc}"
        return

    resume.raw_text = text
    resume.extracted_skills = profile.skills
    resume.extracted_experience_years = profile.experience_years
    resume.extracted_education = [e.model_dump() for e in profile.education]
    resume.extracted_certifications = profile.certifications
    resume.extracted_profile = profile.model_dump()
    resume.extraction_status = ResumeExtractionStatus.DONE
    resume.extracted_at = datetime.now(timezone.utc)

    # Only sourced (bulk, no account yet) resumes get candidate_name/email
    # filled from extraction — self-uploads already identify the person
    # via owner_id, and _to_read() deliberately leaves these blank for
    # self-uploads so it can show "you" instead of a possibly-messy
    # resume-derived name.
    if is_sourced:
        resume.candidate_name = profile.candidate_name
        resume.candidate_email = profile.candidate_email


def _store_one(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    owner_id: uuid.UUID | None,
    uploaded_by: User,
    db: Session,
) -> Resume:
    """Shared upload path for both single and bulk upload: put the bytes in
    blob storage, then persist the row. Raises HTTPException on failure —
    callers decide whether that propagates (single upload) or gets caught
    and reported per-file (bulk upload)."""
    blob_name = build_blob_name(owner_id, filename)
    try:
        blob_path = upload_resume_blob(file_bytes, blob_name, content_type)
        upload_status = ResumeStatus.UPLOADED
    except Exception as exc:
        # A blob-storage failure shouldn't take down the whole request —
        # record it as a FAILED row so it's visible in listings/audit
        # rather than silently vanishing.
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
    if upload_status == ResumeStatus.UPLOADED:
        # Extraction failure is independent of upload success — the file
        # is already safely in blob storage by this point regardless of
        # what happens next, so this only ever affects extraction_status.
        _run_extraction(resume, file_bytes, filename, is_sourced=owner_id is None)
    db.add(resume)
    db.flush()  # assigns resume.id before we snapshot it for the audit row
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
    at most one active resume — a repeat upload replaces the old one
    (deletes the previous blob + row) rather than accumulating versions."""
    contents = await file.read()
    _validate_upload(file.content_type, len(contents))

    existing = (
        db.query(Resume)
        .filter(Resume.owner_id == current_user.id, Resume.is_archived.is_(False))
        .first()
    )
    if existing is not None:
        delete_resume_blob(existing.blob_path)
        record_audit(
            db, actor=current_user, action="delete", resource_type="resume",
            resource_id=existing.id, before=snapshot(existing, "resume"),
        )
        db.delete(existing)
        db.flush()  # old row must be gone before the new one lands, in case
                    # a future unique constraint on (owner_id, is_archived) is added

    resume = _store_one(contents, file.filename, file.content_type, current_user.id, current_user, db)
    db.commit()
    db.refresh(resume)
    return resume


@router.post("/bulk", response_model=list[ResumeBulkUploadResult])
async def upload_resumes_bulk(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    """Recruiter/admin sourcing upload. No per-file candidate metadata yet
    (owner_id stays null) — Phase 4 parsing fills in candidate_name/email
    once it reads the file, rather than trusting free-text at upload time.
    Each file succeeds or fails independently; one bad file in a batch of
    fifty shouldn't sink the other forty-nine."""
    results: list[ResumeBulkUploadResult] = []
    for file in files:
        contents = await file.read()
        # Each file gets its own SAVEPOINT (via db.begin_nested()). A plain
        # db.rollback() rolls back the *entire* outer transaction, wiping
        # out every earlier success staged in this same loop — not just the
        # current file's work. Scoping the rollback to a nested transaction
        # is what actually makes "one bad file in a batch of fifty shouldn't
        # sink the other forty-nine" true, instead of just documented.
        try:
            with db.begin_nested():
                _validate_upload(file.content_type, len(contents))
                resume = _store_one(contents, file.filename, file.content_type, None, current_user, db)
                db.flush()
            results.append(ResumeBulkUploadResult(
                original_filename=file.filename, success=True,
                resume=ResumeRead.model_validate(resume),
            ))
        except HTTPException as exc:
            # The `with db.begin_nested()` block already rolled back to the
            # savepoint on exception — earlier successes in this loop stay
            # staged for the final commit below.
            results.append(ResumeBulkUploadResult(
                original_filename=file.filename, success=False, error=exc.detail,
            ))

    db.commit()
    return results


def _get_visible_resume(resume_id: uuid.UUID, db: Session, current_user: User) -> Resume:
    resume = db.get(Resume, resume_id)
    is_privileged = current_user.role in (UserRole.RECRUITER, UserRole.ADMIN, UserRole.SUPERUSER)
    if resume is None or (not is_privileged and resume.owner_id != current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    return resume


def _get_manageable_resume(resume_id: uuid.UUID, db: Session, current_user: User) -> Resume:
    """Write-access lookup for archive/delete: the owning candidate, the
    recruiter/admin who uploaded it, or any admin/superuser. A recruiter
    who did NOT source a given self-uploaded resume has no write access to
    it — same 404-for-both pattern as jobs, to avoid leaking existence."""
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
    """Attaches owner/uploader email on top of the plain column mapping —
    self-uploaded resumes have no candidate_name/candidate_email (only
    recruiter-sourced ones do), so without this a recruiter browsing the
    library sees a bare UUID instead of who the resume belongs to."""
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
    """USER sees only their own resume(s); recruiter/admin/superuser see
    every resume in the system, same visibility split as list_users."""
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
    resume = _get_visible_resume(resume_id, db, current_user)
    if settings.STORAGE_BACKEND == "azure":
        return RedirectResponse(get_resume_download_url(resume.blob_path))
    from app.core.storage.local_disk import read_blob
    try:
        contents = read_blob(resume.blob_path)
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