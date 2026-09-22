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

    # LLM extraction backend. "ollama" (default) routes both extraction
    # calls at a local, self-hosted Ollama server -- no GPU, no per-token
    # billing, no HF_TOKEN needed. Set to "hf" to route through Hugging
    # Face Inference Providers instead (paid, needs HF_TOKEN below).
    #
    # hf_client.get_client(provider) special-cases provider == "ollama":
    # it points the same huggingface_hub InferenceClient at Ollama's
    # local OpenAI-compatible endpoint (base_url) instead of HF's router,
    # so llm_extract.py / skills_llm_extract.py needed zero changes --
    # they still just call client.chat_completion(model=..., response_
    # format=...) and Ollama (v0.5+) enforces that response_format's
    # json_schema itself via llama.cpp's grammar-constrained decoder.
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # We only ever use Qwen2-1.5B-Instruct now, so both the full-profile
    # extraction call and the standalone skills call point at the same
    # local model/provider. Model id is the Ollama tag, not the HF repo
    # id -- `ollama pull hf.co/QuantFactory/Qwen2-1.5B-Instruct-GGUF:Q4_K_M`
    # pulls the exact HF checkpoint, Q4_K_M-quantized for CPU efficiency.
    HF_INFERENCE_PROVIDER: str = "ollama"
    HF_EXTRACTION_MODEL: str = "hf.co/QuantFactory/Qwen2-1.5B-Instruct-GGUF:Q4_K_M"
    HF_SKILLS_MODEL: str | None = "hf.co/QuantFactory/Qwen2-1.5B-Instruct-GGUF:Q4_K_M"
    HF_SKILLS_PROVIDER: str | None = "ollama"

    # Only needed if HF_INFERENCE_PROVIDER/HF_SKILLS_PROVIDER is switched
    # back to a real Hugging Face provider (e.g. "cerebras"). Needs the
    # "Make calls to Inference Providers" permission from your HF account.
    HF_TOKEN: str | None = None

    # Redis / Celery (extraction queue)
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None

    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
    )

settings = Settings()