"""
Shared cache of Hugging Face `InferenceClient` instances, keyed by
provider name (e.g. "cerebras", "groq").

Both app/core/llm_extract.py (full candidate-profile / job extraction)
and app/core/skills_llm_extract.py (the standalone skills-only
extraction path) talk to the same Hugging Face account, so they share
one client cache instead of each module opening its own connection pool
per provider. Previously llm_extract.py defined this cache-and-getter
twice in the same file (once near the top, once again further down) --
consolidating it here also removes that duplication.
"""

from huggingface_hub import InferenceClient

from app.core.config import settings

HF_TIMEOUT_SECONDS = 30

_clients: dict[str, InferenceClient] = {}


def get_client(provider: str) -> InferenceClient:
    if provider not in _clients:
        _clients[provider] = InferenceClient(
            provider=provider,
            api_key=settings.HF_TOKEN,
            timeout=HF_TIMEOUT_SECONDS,
        )
    return _clients[provider]