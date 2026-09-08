import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, require_recruiter_or_admin, require_admin_or_superuser, require_superuser
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.user import UserRead, UserPublicRead, UserRoleUpdate, UserActiveUpdate

router = APIRouter()

@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.get("")
def list_users(
    pending: bool = False,
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
    users = query.all()

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

    target.is_active = payload.is_active
    if payload.is_active and target.requested_role == UserRole.RECRUITER:
        target.role = UserRole.RECRUITER
        target.requested_role = None

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
    target.requested_role = None
    target.recruiter_rejected_at = func.now()
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
    target.role = payload.role
    if payload.role == UserRole.ADMIN:
        # a newly promoted admin should be usable immediately, not stuck
        # pending approval — they were already an approved user before promotion
        target.is_active = True
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

    # demote first, then promote — never two SUPERUSER rows at once;
    # the DB's unique partial index is the backstop if this order
    # were ever reversed by a future bug
    current_user.role = UserRole.USER
    db.flush()
    target.role = UserRole.SUPERUSER
    target.is_active = True
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
    db.delete(target)
    db.commit()