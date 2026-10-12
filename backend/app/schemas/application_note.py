import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_NOTE_LENGTH = 2000


class ApplicationNoteCreate(BaseModel):
    body: str = Field(max_length=MAX_NOTE_LENGTH)

    @field_validator("body")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        # Strip first so "   " and "\n" are rejected as empty, and stored
        # notes never carry stray leading/trailing whitespace.
        value = value.strip()
        if not value:
            raise ValueError("Note cannot be empty")
        return value


class ApplicationNoteRead(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    author_id: uuid.UUID | None  # None once the author's account is deleted
    author_email: str | None
    body: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ManualScoreUpdate(BaseModel):
    # No default on purpose: pydantic v2 treats an Optional field with no
    # default as *required*, so the client must say what it means. A number
    # sets the score; an explicit null clears it. An empty body {} is a 422
    # instead of silently wiping the score.
    manual_score: float | None = Field(ge=0, le=100, allow_inf_nan=False)


class ManualScoreRead(BaseModel):
    id: uuid.UUID
    manual_score: float | None
    model_config = ConfigDict(from_attributes=True)
