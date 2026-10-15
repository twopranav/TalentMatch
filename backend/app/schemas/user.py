import re
import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict, field_validator, model_validator
from app.models.user import SubCompany, UserRole


def _validate_password_strength(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"[A-Za-z]", value):
        raise ValueError("Password must contain at least one letter")
    if not re.search(r"[0-9]", value):
        raise ValueError("Password must contain at least one number")
    return value


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    phone: str | None = None
    # What the signer-upper is asking to be. Defaults to USER so existing
    # clients that don't send this field are unaffected. Recruiter and admin
    # are requests only (the superuser grants them); superuser can never be
    # requested through signup.
    role: UserRole = UserRole.USER
    sub_company: SubCompany | None = None

    @model_validator(mode="after")
    def staff_needs_sub_company(self):
        if self.role in (UserRole.RECRUITER, UserRole.ADMIN) and self.sub_company is None:
            raise ValueError("sub_company is required when requesting recruiter or admin access")
        return self

    @field_validator("role")
    @classmethod
    def restrict_signup_role(cls, value: UserRole) -> UserRole:
        if value not in (UserRole.USER, UserRole.RECRUITER, UserRole.ADMIN):
            raise ValueError("role must be 'user', 'recruiter' or 'admin' at signup")
        return value

    @field_validator("password")
    @classmethod
    def check_password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)

class UserRead(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    requested_role: UserRole | None
    recruiter_rejected_at: datetime | None
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
    avatar_url: str | None = None
    sub_company: SubCompany | None = None
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

class ChangePassword(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)


class DeleteAccount(BaseModel):
    """Body of DELETE /users/me: the caller re-enters their password."""
    password: str


class UserSubCompanyUpdate(BaseModel):
    sub_company: SubCompany | None
