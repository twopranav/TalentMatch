import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.audit import record_audit, snapshot
from app.core.config import settings
from app.core.resume_storage import build_blob_name, delete_resume_blob, get_resume_download_url, upload_resume_blob
from app.core.deps import get_current_user, require_recruiter_or_admin, require_admin_or_superuser, require_superuser
from app.db.session import get_db
from app.models.job import Job
from app.models.user import User, UserRole
from app.schemas.user import UserRead, UserPublicRead, UserRoleUpdate, UserActiveUpdate, UserProfileUpdate

router = APIRouter()

_ALLOWED_AVATAR_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_AVATAR_UPLOAD_BYTES = 5 * 1024 * 1024

def _serialize_user(user: User) -> UserRead:
    data = UserRead.model_validate(user).model_dump()
    data["avatar_url"] = f"/api/users/{user.id}/avatar/file" if user.avatar_blob_path else None
    return UserRead(**data)

@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)):
    return _serialize_user(current_user)

@router.patch("/me", response_model=UserRead)
def update_me(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Self-service profile edit — any authenticated user can update their
    own non-role, non-security fields. Role, is_active, email, and password
    all have their own dedicated endpoints and are deliberately excluded
    from UserProfileUpdate, so there's no privilege-escalation surface here."""
    before = snapshot(current_user, "user")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(current_user, field, value)
    if updates:
        record_audit(
            db, actor=current_user, action="update", resource_type="user",
            resource_id=current_user.id, before=before, after=snapshot(current_user, "user"),
        )
    db.commit()
    db.refresh(current_user)
    return _serialize_user(current_user)

@router.post("/me/avatar", response_model=UserRead)
async def upload_avatar(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if file.content_type not in _ALLOWED_AVATAR_CONTENT_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Avatar must be a JPEG, PNG, or WebP image.")
    contents = await file.read()
    if len(contents) > _MAX_AVATAR_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Avatar file must be under 5 MB.")
    if current_user.avatar_blob_path:
        delete_resume_blob(current_user.avatar_blob_path)
    before = snapshot(current_user, "user")
    blob_name = build_blob_name(current_user.id, file.filename)
    current_user.avatar_blob_path = upload_resume_blob(contents, blob_name, file.content_type)
    record_audit(db, actor=current_user, action="update", resource_type="user", resource_id=current_user.id, before=before, after=snapshot(current_user, "user"))
    db.commit(); db.refresh(current_user)
    return _serialize_user(current_user)

@router.get("/{user_id}/avatar/file")
def get_avatar_file(user_id: uuid.UUID, db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target is None or not target.avatar_blob_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No avatar on file")
    if settings.STORAGE_BACKEND == "azure":
        return RedirectResponse(get_resume_download_url(target.avatar_blob_path))
    from app.core.storage.local_disk import read_blob
    try:
        contents = read_blob(target.avatar_blob_path)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar file is missing from storage.")
    ext = target.avatar_blob_path.rsplit(".", 1)[-1].lower()
    media_type = {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png","webp":"image/webp"}.get(ext, "application/octet-stream")
    return Response(content=contents, media_type=media_type)

@router.get("")
def list_users(
    pending: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    """
    pending=true filters to accounts with an unreviewed recruiter request
    (requested_role is not null). Only admins/superusers may use this filter
    — a recruiter listing users has no legitimate reason to see who else is
    waiting on approval, so this is checked separately from the normal
    admin-vs-recruiter schema trim below.
    """
    if pending and current_user.role not in (UserRole.ADMIN, UserRole.SUPERUSER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view pending requests.",
        )

    query = db.query(User)
    if pending:
        query = query.filter(User.requested_role.isnot(None))
    users = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()

    if current_user.role in (UserRole.ADMIN, UserRole.SUPERUSER):
        return [UserRead.model_validate(u) for u in users]
    return [UserPublicRead.model_validate(u) for u in users]

@router.get("/{user_id}")
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(require_recruiter_or_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if current_user.role in (UserRole.ADMIN, UserRole.SUPERUSER):
        return UserRead.model_validate(user)
    return UserPublicRead.model_validate(user)

def _assert_can_edit_profile(current_user: User, target: User) -> None:
    """Permission rule for PATCH /users/{user_id} (admin/superuser editing
    someone else's profile fields — NOT role or active-status changes,
    those have their own endpoints with their own rules).

    - SUPERUSER: can edit anyone.
    - ADMIN: can edit USER and RECRUITER accounts only — not other admins,
      not the superuser. Symmetric with update_admin_status below, which is
      superuser-only precisely because no admin should be able to touch
      another admin's account.
    - Anyone else calling this: caught earlier by the require_admin_or_superuser
      dependency, so recruiters/users never reach this function. They edit
      their own profile via PATCH /users/me instead.
    """
    if current_user.role == UserRole.SUPERUSER:
        return
    if current_user.role == UserRole.ADMIN and target.role in (UserRole.USER, UserRole.RECRUITER):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admins can only edit user and recruiter accounts, not other admins.",
    )

@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: uuid.UUID,
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_superuser),
):
    """Admin/superuser edit of another user's profile fields (name, phone,
    company, title, skills, experience, location, desired_role). Reuses
    UserProfileUpdate — the same schema /me uses — so this can never touch
    role, is_active, email, or password; those stay on their dedicated
    endpoints. See _assert_can_edit_profile for who can edit whom.
    """
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    _assert_can_edit_profile(current_user, target)

    before = snapshot(target, "user")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(target, field, value)
    if updates:
        record_audit(
            db, actor=current_user, action="update", resource_type="user",
            resource_id=target.id, before=before, after=snapshot(target, "user"),
        )
    db.commit()
    db.refresh(target)
    return _serialize_user(target)

@router.patch("/{user_id}/active", response_model=UserRead)
def update_user_active(
    user_id: uuid.UUID,
    payload: UserActiveUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_superuser),
):
    """Approve (activate) or deactivate a recruiter/user account.
    Any admin or the superuser can do this — this is the routine,
    frequent action, unlike role changes below.

    If the account signed up requesting RECRUITER (requested_role is set)
    and this call activates it (is_active=True), that request is granted:
    role becomes RECRUITER and requested_role is cleared. Deactivating, or
    activating an account with no pending request, never touches role —
    an unapproved recruiter signup simply stays a USER.
    """
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.role == UserRole.SUPERUSER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate the superuser account.")

    before = snapshot(target, "user")
    target.is_active = payload.is_active
    if payload.is_active and target.requested_role == UserRole.RECRUITER:
        target.role = UserRole.RECRUITER
        target.requested_role = None

    record_audit(
        db, actor=current_user, action="update", resource_type="user",
        resource_id=target.id, before=before, after=snapshot(target, "user"),
    )
    db.commit()
    db.refresh(target)
    return target

@router.post("/{user_id}/reject-recruiter-request", response_model=UserRead)
def reject_recruiter_request(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_superuser),
):
    """
    Explicitly decline a pending recruiter signup request. This is the
    counterpart to the auto-promotion in update_user_active above: that one
    fires on approval, this one fires on denial. Clears requested_role (so
    it drops out of the pending filter) and stamps recruiter_rejected_at,
    which is the only way to later tell "never asked" apart from "asked,
    got turned down" — both otherwise look identical (requested_role=None,
    role=USER). role and is_active are untouched: rejecting a recruiter
    request does not deactivate or otherwise punish the underlying account,
    it just closes out the request.
    """
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.requested_role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This user has no pending recruiter request.",
        )
    before = snapshot(target, "user")
    target.requested_role = None
    target.recruiter_rejected_at = func.now()
    db.flush()  # so the snapshot below reflects the server-set recruiter_rejected_at
    record_audit(
        db, actor=current_user, action="update", resource_type="user",
        resource_id=target.id, before=before, after=snapshot(target, "user"),
    )
    db.commit()
    db.refresh(target)
    return target

@router.patch("/{user_id}/admin-status", response_model=UserRead)
def update_admin_status(
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Promote a user to ADMIN, or demote an ADMIN back to USER.
    Superuser-only — no admin, however senior, can create or remove
    another admin. This endpoint never touches SUPERUSER; use
    /transfer-superuser for that."""
    if payload.role not in (UserRole.ADMIN, UserRole.USER):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This endpoint only promotes to ADMIN or demotes to USER.",
        )
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.role == UserRole.SUPERUSER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change the superuser's role here. Use /transfer-superuser.",
        )
    before = snapshot(target, "user")
    target.role = payload.role
    if payload.role == UserRole.ADMIN:
        # a newly promoted admin should be usable immediately, not stuck
        # pending approval — they were already an approved user before promotion
        target.is_active = True
    record_audit(
        db, actor=current_user, action="update", resource_type="user",
        resource_id=target.id, before=before, after=snapshot(target, "user"),
    )
    db.commit()
    db.refresh(target)
    return target

@router.post("/{user_id}/transfer-superuser", response_model=UserRead)
def transfer_superuser(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Reassign the single SUPERUSER seat. The outgoing superuser is
    stripped all the way to USER — not ADMIN — per spec: the new
    superuser decides independently whether to promote them back."""
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You are already the superuser.")
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    before_current = snapshot(current_user, "user")
    before_target = snapshot(target, "user")

    # demote first, then promote — never two SUPERUSER rows at once;
    # the DB's unique partial index is the backstop if this order
    # were ever reversed by a future bug
    current_user.role = UserRole.USER
    db.flush()
    target.role = UserRole.SUPERUSER
    target.is_active = True
    db.flush()

    # two rows are mutated here, so two audit entries — one per affected user
    record_audit(
        db, actor=current_user, action="update", resource_type="user",
        resource_id=current_user.id, before=before_current, after=snapshot(current_user, "user"),
    )
    record_audit(
        db, actor=current_user, action="update", resource_type="user",
        resource_id=target.id, before=before_target, after=snapshot(target, "user"),
    )
    db.commit()
    db.refresh(target)
    return target

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_superuser)):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.role == UserRole.SUPERUSER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transfer superuser status to another account before deleting it.",
        )
    # Job.created_by has cascade="all, delete-orphan" — deleting this user
    # would silently delete every job they ever created, and each of THOSE
    # deletions cascades to delete every application on that job. That's a
    # lot of unrelated candidates' application history to lose because one
    # recruiter's account got removed. Block it and make reassignment
    # explicit instead of allowing an accidental mass-delete.
    owned_job_count = db.query(func.count(Job.id)).filter(Job.created_by_id == target.id).scalar()
    if owned_job_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"This user still owns {owned_job_count} job posting(s). "
                "Reassign or close those jobs before deleting the account."
            ),
        )
    record_audit(
        db, actor=current_user, action="delete", resource_type="user",
        resource_id=target.id, before=snapshot(target, "user"),
    )
    db.delete(target)
    db.commit()