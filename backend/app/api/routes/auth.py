from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core.security import hash_password, verify_password, create_access_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserRead, Token

router = APIRouter()

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    # Signup never writes role=RECRUITER directly, no matter what was asked
    # for. If they asked for RECRUITER, that request is only *recorded* in
    # requested_role — the account is a plain, functional USER (role stays
    # at the model default) until an admin approves it via PATCH .../active.
    requested_role = payload.role if payload.role == UserRole.RECRUITER else None

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        requested_role=requested_role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)  # pulls back server-generated fields: id (default=uuid4 fired here), created_at
    return user

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    user = db.query(User).filter(User.email == form_data.username).first()
    # OAuth2PasswordRequestForm always calls the field "username" — we're
    # treating email as the username, which is why form_data.username is the email.
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=str(user.id), extra_claims={"role": user.role.value})
    return Token(access_token=token)