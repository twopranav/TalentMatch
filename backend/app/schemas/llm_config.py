from pydantic import BaseModel, field_validator

from app.core.llm_provider_registry import PROVIDERS


class LLMConfigRead(BaseModel):
    task: str
    provider: str
    model: str

    model_config = {"from_attributes": True}


class LLMConfigUpdate(BaseModel):
    provider: str
    model: str

    @field_validator("provider")
    @classmethod
    def provider_must_be_registered(cls, v: str) -> str:
        if v not in PROVIDERS:
            raise ValueError(f"Unknown provider {v!r}. Available: {sorted(PROVIDERS)}")
        return v
