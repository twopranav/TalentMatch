import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict
from app.models.user import UserRole

class UserCreate(BaseModel):
    email: EmailStr
    password: str  # plaintext in, only ever hashed before it touches the DB

class UserRead(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
    # ^ lets you do UserRead.model_validate(some_user_orm_object) — Pydantic
    #   normally only reads dicts; this tells it to read attributes off an
    #   arbitrary Python object (your SQLAlchemy instance) instead.

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserPublicRead(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    model_config = ConfigDict(from_attributes=True)

class UserRoleUpdate(BaseModel):
    role: UserRole