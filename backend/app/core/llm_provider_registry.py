"""
Registry of chat-model providers the admin UI's "active model" dropdown
can select from (llm_configs.provider -> a builder function here).

Everything downstream (llm_client.py, llm_json_call.py, the Celery
tasks) only ever sees a LangChain BaseChatModel. Nothing outside this
file knows which vendor is behind it, so:

  * new MODEL on an existing provider -> no code, edit the llm_configs
    row (PUT /api/admin/llm-config/{task}).
  * new PROVIDER -> one builder function + one PROVIDERS entry below,
    plus its credential in config.py. Nothing else changes.

Rules every builder follows, so providers stay interchangeable:
  - temperature=0 (extraction must be deterministic-ish)
  - a hard timeout
  - max_retries=0: retrying belongs to Celery (with backoff, see the
    extraction tasks). SDK-level retries on top would multiply calls
    against a rate-limited provider such as Groq's free tier.
  - imports are LAZY, so a provider's package only has to be installed
    if a task is actually pointed at it.
  - a missing credential raises LLMConfigError with a readable message,
    which the tasks record as the row's skills_extraction_error.
"""

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import settings

_TIMEOUT_SECONDS = 30


class LLMConfigError(Exception):
    """A task can't get a working model: unset row, unknown provider,
    or a missing credential. Permanent until someone fixes config, so
    the tasks fail the row immediately instead of retrying."""


def _require(value: str | None, env_name: str, provider: str) -> str:
    if not value:
        raise LLMConfigError(
            f"Provider {provider!r} selected but {env_name} is not set in the environment."
        )
    return value


def _groq(model: str) -> BaseChatModel:
    # pip install langchain-groq
    from langchain_groq import ChatGroq

    return ChatGroq(
        model=model,
        temperature=0,
        api_key=_require(settings.GROQ_API_KEY, "GROQ_API_KEY", "groq"),
        timeout=_TIMEOUT_SECONDS,
        max_retries=0,
    )


def _openai(model: str) -> BaseChatModel:
    # pip install langchain-openai
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        api_key=_require(settings.OPENAI_API_KEY, "OPENAI_API_KEY", "openai"),
        model=model,
        temperature=0,
        timeout=_TIMEOUT_SECONDS,
        max_retries=0,
    )


def _huggingface(model: str) -> BaseChatModel:
    # HF Inference Providers router is OpenAI-compatible. Pick the
    # backend by suffixing the model id ("repo/model:provider").
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        base_url="https://router.huggingface.co/v1",
        api_key=_require(settings.HF_TOKEN, "HF_TOKEN", "huggingface"),
        model=model,
        temperature=0,
        timeout=_TIMEOUT_SECONDS,
        max_retries=0,
    )


PROVIDERS: dict[str, callable] = {
    "groq": _groq,
    "openai": _openai,
    "huggingface": _huggingface,
}