"""
Central app configuration, loaded from environment variables (.env).
Nothing else in the app should call os.environ directly — import `settings` instead.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App
    APP_NAME: str = "Resume Filter Application"
    ENV: str = "development"  # development | staging | production
    DEBUG: bool = True

    # Postgres
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/talentdb"

    # Auth / JWT
    JWT_SECRET_KEY: str = "change-me-in-env"  # override in .env, never commit a real secret
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Azure Blob / ADLS
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_STORAGE_CONTAINER: str = "resumes"

    # CORS — frontend origin(s) allowed to call this API
    CORS_ORIGINS: list[str] = ["http://localhost:5173"] 
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()