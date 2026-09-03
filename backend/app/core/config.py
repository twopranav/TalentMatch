from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    # App
    APP_NAME: str = "Resume Filter Application"
    ENV: str = "development"
    DEBUG: bool = True

    # Postgres
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/talentdb"

    # Auth / JWT
    JWT_SECRET_KEY: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Azure Blob / ADLS
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_STORAGE_CONTAINER: str = "resumes"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
    )

settings = Settings()