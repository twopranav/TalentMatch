import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session
from app.core.audit import record_audit, snapshot
from app.core.deps import get_current_user, require_recruiter_or_admin
from app.core.resume_storage import build_blob_name, delete_resume_blob, get_resume_download_url, upload_resume_blob
from app.db.session import get_db
from app.models.resume import Resume, ResumeStatus
from app.models.user import User, UserRole
from app.schemas.resume import ResumeBulkUploadResult, ResumeRead, ResumeReadWithUrl

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
        try:
            _validate_upload(file.content_type, len(contents))
            resume = _store_one(contents, file.filename, file.content_type, None, current_user, db)
            db.flush()
            results.append(ResumeBulkUploadResult(
                original_filename=file.filename, success=True,
                resume=ResumeRead.model_validate(resume),
            ))
        except HTTPException as exc:
            # Roll back only this file's partial state, not the whole batch —
            # successes recorded earlier in the loop stay staged for commit.
            db.rollback()
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
    query = db.query(Resume)
    if current_user.role == UserRole.USER:
        query = query.filter(Resume.owner_id == current_user.id)
    if not include_archived:
        query = query.filter(Resume.is_archived.is_(False))
    return query.order_by(Resume.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/{resume_id}", response_model=ResumeReadWithUrl)
def get_resume(resume_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    resume = _get_visible_resume(resume_id, db, current_user)
    download_url = get_resume_download_url(resume.blob_path)
    return ResumeReadWithUrl(**ResumeRead.model_validate(resume).model_dump(), download_url=download_url)


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
