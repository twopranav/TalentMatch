from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    APP_NAME: str = "Resume Filter Application"
    ENV: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/talentdb"

    JWT_SECRET_KEY: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    STORAGE_BACKEND: str = "local"  # "local" or "azure"
    AZURE_STORAGE_SAS_URL: str | None = None
    LOCAL_STORAGE_ROOT: str = "./storage/resumes"

    # Connection details for each provider the admin UI can point a task
    # at (app/core/llm_provider_registry.py). Which provider+model a
    # given task (resume_skills, jd_skills) actually uses lives in the
    # llm_configs DB table now, not here -- these are only the
    # credentials/endpoints a provider needs regardless of which model
    # is selected, and still belong in the environment, not the DB.

    # Needs the "Make calls to Inference Providers" permission from your
    # HF account. Only required if a task's llm_configs row uses
    # provider="huggingface".
    HF_TOKEN: str | None = None

    # Only required if a task's llm_configs row uses provider="openai".
    OPENAI_API_KEY: str | None = None

    GROQ_API_KEY: str | None = None
    LLM_QUEUE_NAME: str = "llm"
    LLM_TASK_RATE_LIMIT: str | None = None  # e.g. "20/m", per worker

    # Redis / Celery (extraction queue)
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None

    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()