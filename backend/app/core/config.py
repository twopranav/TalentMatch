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

    # --- Applicant matching score (app/core/semantic_match.py) ---
    # "hf" = Hugging Face Inference API (needs HF_TOKEN); "local" =
    # sentence-transformers in-process (pip install sentence-transformers).
    EMBEDDING_PROVIDER: str = "hf"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Relative weights; a component the JD sets no requirement for (e.g. no
    # minimum experience) is dropped and the rest renormalised.
    MATCH_WEIGHT_SKILLS: float = 0.8
    MATCH_WEIGHT_EXPERIENCE: float = 0.2

    # Cosine similarity mapped to per-skill credit: <= LOW earns 0,
    # >= HIGH earns 1, linear in between. An exact match after alias
    # normalisation always earns 1 without calling the embedder.
    MATCH_SIM_LOW: float = 0.40
    MATCH_SIM_HIGH: float = 0.85

    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()