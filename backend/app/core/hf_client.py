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
        if provider == "ollama":
            # Ollama isn't a real HF Inference Provider -- point the same
            # InferenceClient at Ollama's local OpenAI-compatible endpoint
            # via base_url instead of the HF router. api_key is ignored by
            # Ollama, but the client still forms an `Authorization: Bearer
            # <key>` header locally before any request goes out, and an
            # empty/None key produces a malformed header ("Bearer ") that
            # httpx rejects before it ever reaches the network -- so this
            # needs *some* non-empty placeholder, not settings.HF_TOKEN.
            _clients[provider] = InferenceClient(
                base_url=f"{settings.OLLAMA_BASE_URL}/v1",
                api_key="ollama",
                timeout=HF_TIMEOUT_SECONDS,
            )
        else:
            _clients[provider] = InferenceClient(
                provider=provider,
                api_key=settings.HF_TOKEN,
                timeout=HF_TIMEOUT_SECONDS,
            )
    return _clients[provider]