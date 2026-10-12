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

import re

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


# Models that accept a reasoning_effort parameter. Sending it to any other
# model can make the API reject the request, so it is gated by model name.
_REASONING_MODELS = re.compile(r"(gpt-oss|(^|/)o[134](-|$)|gpt-5)", re.IGNORECASE)


def _common_kwargs(model: str, overrides: dict, *, allow_reasoning: bool) -> dict:
    """Translate the generic per-task overrides (max_tokens, reasoning_effort)
    into constructor kwargs. Anything the target model doesn't support is
    dropped, so swapping the model in the admin UI never causes a
    bad-parameter error."""
    kw: dict = {}
    if overrides.get("max_tokens"):
        kw["max_tokens"] = overrides["max_tokens"]
    if (
        allow_reasoning
        and overrides.get("reasoning_effort")
        and _REASONING_MODELS.search(model)
    ):
        kw["reasoning_effort"] = overrides["reasoning_effort"]
    return kw


def _groq(model: str, **overrides) -> BaseChatModel:
    from langchain_groq import ChatGroq

    return ChatGroq(
        model=model,
        temperature=0,
        api_key=_require(settings.GROQ_API_KEY, "GROQ_API_KEY", "groq"),
        timeout=overrides.get("timeout", _TIMEOUT_SECONDS),
        max_retries=0,
        **_common_kwargs(model, overrides, allow_reasoning=True),
    )


def _openai(model: str, **overrides) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        api_key=_require(settings.OPENAI_API_KEY, "OPENAI_API_KEY", "openai"),
        model=model,
        temperature=0,
        timeout=overrides.get("timeout", _TIMEOUT_SECONDS),
        max_retries=0,
        **_common_kwargs(model, overrides, allow_reasoning=True),
    )


def _huggingface(model: str, **overrides) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        base_url="https://router.huggingface.co/v1",
        api_key=_require(settings.HF_TOKEN, "HF_TOKEN", "huggingface"),
        model=model,
        temperature=0,
        timeout=overrides.get("timeout", _TIMEOUT_SECONDS),
        max_retries=0,
        **_common_kwargs(model, overrides, allow_reasoning=False),
    )


PROVIDERS: dict[str, callable] = {
    "groq": _groq,
    "openai": _openai,
    "huggingface": _huggingface,
}