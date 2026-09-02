import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, require_admin, require_recruiter_or_admin
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.user import UserRead, UserPublicRead, UserRoleUpdate

router = APIRouter()

@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.get("")
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_recruiter_or_admin)):
    users = db.query(User).all()
    # No response_model here on purpose: the shape returned depends on the
    # caller's role, and FastAPI's Union response_model handling doesn't
    # reliably pick the narrower schema — so we serialize explicitly instead.
    if current_user.role == UserRole.ADMIN:
        return [UserRead.model_validate(u) for u in users]
    return [UserPublicRead.model_validate(u) for u in users]

@router.get("/{user_id}")
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(require_recruiter_or_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if current_user.role == UserRole.ADMIN:
        return UserRead.model_validate(user)
    return UserPublicRead.model_validate(user)

@router.patch("/{user_id}/role", response_model=UserRead)
def update_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if payload.role == UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use /users/{id}/transfer-admin to change the admin.",
        )
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.role == UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change the current admin's role through this endpoint.",
        )
    target.role = payload.role
    db.commit()
    db.refresh(target)
    return target

@router.post("/{user_id}/transfer-admin", response_model=UserRead)
def transfer_admin(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You are already the admin.")
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    # Demote first, then promote — never both ADMIN in the same instant.
    # The unique index in the migration is the DB-level backstop if this
    # order were ever reversed by a future bug.
    current_user.role = UserRole.USER
    db.flush()
    target.role = UserRole.ADMIN
    db.commit()
    db.refresh(target)
    return target

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transfer admin status to another user before deleting your account.",
        )
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db.delete(target)
    db.commit()