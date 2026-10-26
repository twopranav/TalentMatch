from pathlib import Path
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    APP_NAME: str = "Resume Filter Application"
    ENV: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/talentdb"

    JWT_SECRET_KEY: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    # Short on purpose: the browser silently renews it from the refresh
    # cookie (POST /api/auth/refresh), so users never notice, but a stolen
    # access token is only good for this long.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

    # --- Browser sessions (app/core/sessions.py, routes/auth.py) ---
    # A login creates a row in user_sessions and sets three cookies:
    #   tm_access   httpOnly access JWT, lives ACCESS_TOKEN_EXPIRE_MINUTES
    #   tm_refresh  httpOnly opaque refresh token, only sent to /api/auth,
    #               a session cookie (gone when the browser is closed)
    #   tm_csrf     readable double-submit token the frontend echoes back in
    #               the X-CSRF-Token header on every state-changing request
    # The session ends when it has been idle for SESSION_IDLE_MINUTES (checked
    # at refresh time, so effectively 30 min give or take one access-token
    # lifetime), when SESSION_MAX_HOURS have passed since login, or when it is
    # revoked (logout, logout-all, refresh-token reuse).
    SESSION_IDLE_MINUTES: int = 30
    SESSION_MAX_HOURS: int = 12
    # Two tabs refreshing at the same moment both present the same old
    # refresh token; the loser is allowed this long after the rotation
    # instead of being treated as token theft.
    SESSION_REFRESH_GRACE_SECONDS: int = 10
    # None = "Secure" in production, off otherwise (plain http://localhost).
    COOKIE_SECURE: bool | None = None
    COOKIE_SAMESITE: str = "lax"  # access + csrf cookies; refresh is always strict
    ACCESS_COOKIE_NAME: str = "tm_access"
    REFRESH_COOKIE_NAME: str = "tm_refresh"
    CSRF_COOKIE_NAME: str = "tm_csrf"

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
    EMBEDDING_PROVIDER: str = "local"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Final score = 100 x (W_SKILLS * skills_score + W_EXPERIENCE * experience_score)
    # The two weights are normalised, so only their ratio matters.
    #   experience_score = 1 - exp(-months / SCALE)
    # SCALE is the curve speed in months; at 48, 3 yrs is ~0.53 of the way,
    # 8 yrs ~0.86, 12 yrs ~0.95. Unknown experience scores 0.
    MATCH_WEIGHT_SKILLS: float = 0.55
    MATCH_WEIGHT_EXPERIENCE: float = 0.45
    MATCH_EXPERIENCE_SCALE_MONTHS: int = 48

    # Cosine similarity mapped to per-skill credit: <= LOW earns 0,
    # >= HIGH earns 1, linear in between. An exact match after alias
    # normalisation always earns 1 without calling the embedder.
    MATCH_SIM_LOW: float = 0.40
    MATCH_SIM_HIGH: float = 0.85

    # Where a resume skill appears sets how much it counts (best source wins):
    # work experience > projects > skills-section mentions.
    MATCH_TIER_WORK: float = 1.0
    MATCH_TIER_PROJECTS: float = 0.70
    MATCH_TIER_MENTION: float = 0.35
    # Share of the 2nd-best supporting skill added on top of the best one.
    MATCH_SUPPORT_RHO: float = 0.25
    # Smoothing for the balance factor (a JD skill with no evidence).
    MATCH_BALANCE_EPS: float = 0.10
    # skills_score = blend of coverage / proof rate / balance (normalised).
    MATCH_BLEND_COVERAGE: float = 0.50
    MATCH_BLEND_PROOF: float = 0.25
    MATCH_BLEND_BALANCE: float = 0.25

    # Client-side throttle for LLM extraction calls (see llm_json_call._throttle).
    # Defaults are Groq's free tier; raise them in .env when moving to a
    # paid tier or another provider.
    LLM_RPM_LIMIT: int = 30
    LLM_TPM_LIMIT: int = 8000

    # "redis" (shared, default) | "memory" (per process) | "off" (tests)
    RATE_LIMIT_BACKEND: str = "redis"

    # Request body ceilings, enforced before any parsing (see request_limits.py).
    MAX_REQUEST_BYTES: int = 12 * 1024 * 1024
    MAX_BULK_REQUEST_BYTES: int = 256 * 1024 * 1024

    # Bulk resume uploads (routes/resumes.py stage_uploads): files are read
    # and validated BULK_CHUNK_SIZE at a time (bounds memory to roughly
    # chunk x 10 MB), and each chunk's blobs are uploaded to storage
    # BULK_UPLOAD_CONCURRENCY at a time, off the event loop.
    BULK_CHUNK_SIZE: int = 16
    BULK_UPLOAD_CONCURRENCY: int = 8

    # Fan-out control (matching_tasks._dispatch_ids, POST .../rescore).
    # Scoring tasks are queued RESCORE_BATCH_SIZE at a time, each later batch
    # starting RESCORE_BATCH_DELAY_SECONDS after the one before it, so a job
    # with thousands of applicants doesn't land on the queue all at once.
    # RESCORE_LOCK_SECONDS: a second rescore of the same job inside this window
    # is ignored (double-click / retry protection).
    RESCORE_BATCH_SIZE: int = 50
    RESCORE_BATCH_DELAY_SECONDS: int = 5
    RESCORE_LOCK_SECONDS: int = 60

    # Celery time limits for the LLM extraction tasks, in seconds. The soft
    # limit stops a pathological file (huge or malformed PDF) from tying up
    # the single worker: the task is marked FAILED with a readable reason.
    # The hard limit kills the task if it ignores the soft one. Only
    # enforced by the prefork pool (the Docker default); ignored by
    # `--pool=solo`, which is what you'd use on Windows.
    EXTRACTION_SOFT_TIME_LIMIT: int = 300
    EXTRACTION_HARD_TIME_LIMIT: int = 330

    # --- Logging / metrics (app/core/logging_config.py, metrics.py) ---
    LOG_LEVEL: str = "INFO"
    # "auto" = json in production, readable text otherwise; or force "json" / "text".
    LOG_FORMAT: str = "auto"
    # GET /metrics (Prometheus). Open in development; in production it is
    # disabled unless this token is set, then requires "Authorization: Bearer <token>".
    METRICS_TOKEN: str | None = None

    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def IS_PRODUCTION(self) -> bool:
        return self.ENV.strip().lower() == "production"

    @property
    def COOKIES_SECURE(self) -> bool:
        return self.IS_PRODUCTION if self.COOKIE_SECURE is None else self.COOKIE_SECURE

    @model_validator(mode="after")
    def _production_guardrails(self):
        """Refuse to boot a production instance with unsafe settings."""
        if not self.IS_PRODUCTION:
            return self
        problems = []
        if self.DEBUG:
            problems.append("DEBUG must be false")
        if self.JWT_SECRET_KEY == "change-me-in-env" or len(self.JWT_SECRET_KEY) < 32:
            problems.append("JWT_SECRET_KEY must be a random value of at least 32 characters")
        if "*" in self.CORS_ORIGINS:
            problems.append("CORS_ORIGINS must list explicit origins, not '*'")
        if self.COOKIE_SECURE is False:
            problems.append("COOKIE_SECURE must not be false (login cookies would travel over plain http)")
        if self.COOKIE_SAMESITE.lower() not in ("lax", "strict"):
            problems.append("COOKIE_SAMESITE must be 'lax' or 'strict'")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self


settings = Settings()
