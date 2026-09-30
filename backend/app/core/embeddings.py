"""
Text -> vector, behind one function: embed(texts).

Provider is chosen by settings.EMBEDDING_PROVIDER:
  "hf"    Hugging Face Inference API (feature-extraction pipeline). Needs
          HF_TOKEN. Sends the whole batch in one request.
  "local" sentence-transformers in-process. Needs the package installed;
          the model is loaded once per process.

Vectors are cached per process by (model, text). Skill strings repeat
heavily across resumes and JDs ("python", "docker"), so after warm-up most
scoring runs need few or no network calls.
"""

import logging
from functools import lru_cache

from app.core.config import settings
from app.core.llm_provider_registry import LLMConfigError

logger = logging.getLogger(__name__)

_HF_TIMEOUT_SECONDS = 30
_CACHE_MAX = 20_000
_cache: dict[tuple[str, str], list[float]] = {}


class EmbeddingError(Exception):
    """The embedding call failed (network, quota, bad response). Transient
    as far as the caller is concerned: the matching task retries it."""


def _embed_hf(texts: list[str]) -> list[list[float]]:
    import httpx

    if not settings.HF_TOKEN:
        raise LLMConfigError(
            "EMBEDDING_PROVIDER='hf' but HF_TOKEN is not set in the environment."
        )
    url = (
        "https://router.huggingface.co/hf-inference/models/"
        f"{settings.EMBEDDING_MODEL}/pipeline/feature-extraction"
    )
    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {settings.HF_TOKEN}"},
            json={"inputs": texts, "options": {"wait_for_model": True}},
            timeout=_HF_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise EmbeddingError(f"HF embedding request failed: {exc}") from exc

    if (
        not isinstance(data, list)
        or len(data) != len(texts)
        or not all(isinstance(v, list) and v and isinstance(v[0], (int, float)) for v in data)
    ):
        raise EmbeddingError(
            "Unexpected embedding response shape (expected one flat vector "
            "per input; is EMBEDDING_MODEL a sentence-embedding model?)."
        )
    return data


@lru_cache(maxsize=1)
def _local_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise LLMConfigError(
            "EMBEDDING_PROVIDER='local' but sentence-transformers is not installed."
        ) from exc
    return SentenceTransformer(settings.EMBEDDING_MODEL)


def _embed_local(texts: list[str]) -> list[list[float]]:
    try:
        return [list(map(float, v)) for v in _local_model().encode(texts)]
    except LLMConfigError:
        raise
    except Exception as exc:
        raise EmbeddingError(f"Local embedding failed: {exc}") from exc


def embed(texts: list[str]) -> list[list[float]]:
    """One vector per input text, in order. Duplicate inputs are embedded once."""
    model = settings.EMBEDDING_MODEL
    missing = list(dict.fromkeys(t for t in texts if (model, t) not in _cache))

    if missing:
        provider = settings.EMBEDDING_PROVIDER
        if provider == "hf":
            vectors = _embed_hf(missing)
        elif provider == "local":
            vectors = _embed_local(missing)
        else:
            raise LLMConfigError(f"Unknown EMBEDDING_PROVIDER {provider!r} (use 'hf' or 'local').")

        if len(_cache) + len(missing) > _CACHE_MAX:
            _cache.clear()
        for text, vec in zip(missing, vectors):
            _cache[(model, text)] = vec

    return [_cache[(model, t)] for t in texts]
