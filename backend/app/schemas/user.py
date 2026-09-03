import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict
from app.models.user import UserRole

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    phone: str | None = None

class UserRead(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    full_name: str | None
    phone: str | None
    is_active: bool
    last_login_at: datetime | None
    company: str | None
    title: str | None
    skills: list[str] | None
    experience_years: int | None
    location: str | None
    desired_role: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserPublicRead(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    full_name: str | None
    model_config = ConfigDict(from_attributes=True)

class UserRoleUpdate(BaseModel):
    role: UserRole

class UserProfileUpdate(BaseModel):
    # self-service profile edit — a user updates their own info, not their role
    full_name: str | None = None
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    skills: list[str] | None = None
    experience_years: int | None = None
    location: str | None = None
    desired_role: str | None = None

class UserActiveUpdate(BaseModel):
    # admin-only: the deactivate/reactivate action
    is_active: bool