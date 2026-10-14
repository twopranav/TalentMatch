"""
Provider-quota limiter shared by every caller of the LLM.

Replaces the old process-local `_WINDOW` list in llm_json_call.py. Three
things changed:

  * Atomic: the check and the reservation happen in ONE Redis Lua script, so
    concurrent callers (several workers, containers, or the API's probe
    endpoint) can no longer all pass the check before any of them records
    its usage.
  * Shared: the rolling window lives in Redis, so every process draws from
    the same RPM/TPM budget. If Redis is unreachable it falls back to a
    process-local window (same logic) and says so in the log.
  * Honest about size: a request whose estimate alone exceeds the token
    budget can never fit, so it is rejected (TokenBudgetError) instead of
    being waved through when the window happens to be empty.

Flow for a caller:  reservation = reserve(est, rpm, tpm)  -> call the
provider -> settle(reservation, actual_tokens).  settle() swaps the
estimate for the real usage, releasing tokens the call didn't use.
A failed call is simply never settled: the estimate stays counted, which
is the conservative choice for a 429/5xx the provider may have counted.

The window is global (one key), matching the previous behaviour where all
tasks shared one budget.
"""

import logging
import threading
import time
import uuid
from dataclasses import dataclass

from app.core import rate_limit
from app.core.metrics import record_quota_event

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60
SAFETY_FACTOR = 0.9  # stay under 90% of the configured limits
KEY = "llmquota:global"


class TokenBudgetError(ValueError):
    """The request's estimated tokens exceed the whole per-window budget."""


@dataclass(frozen=True)
class Reservation:
    id: str
    tokens: int
    backend: str  # "redis" or "memory": settle() goes where reserve() went


def token_budget(tpm_limit: int) -> float:
    return tpm_limit * SAFETY_FACTOR


def fits(est_tokens: int, tpm_limit: int) -> bool:
    """False when this request could never be admitted, however long we wait."""
    return est_tokens <= token_budget(tpm_limit)


# ---------------------------------------------------------------------------
# Redis backend. Entries are sorted-set members "<id>:<tokens>" scored by the
# reservation time in ms, so both the request count (ZCARD) and the token sum
# can be computed for the rolling window inside one script.
# ---------------------------------------------------------------------------

_RESERVE_LUA = """
local now    = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local tokens = tonumber(ARGV[3])
local rpm_cap = tonumber(ARGV[4])
local tpm_cap = tonumber(ARGV[5])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
local entries = redis.call('ZRANGE', KEYS[1], 0, -1, 'WITHSCORES')
local used = 0
local count = 0
for i = 1, #entries, 2 do
  used = used + tonumber(string.match(entries[i], ':(%d+)$'))
  count = count + 1
end
if count < rpm_cap and used + tokens <= tpm_cap then
  redis.call('ZADD', KEYS[1], now, ARGV[6] .. ':' .. tokens)
  redis.call('PEXPIRE', KEYS[1], window * 2)
  return 0
end
if #entries == 0 then return 1000 end
return math.max(tonumber(entries[2]) + window - now, 1)
"""

_SETTLE_LUA = """
local score = redis.call('ZSCORE', KEYS[1], ARGV[1])
if not score then return 0 end
redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('ZADD', KEYS[1], score, ARGV[2])
return 1
"""


def _redis():
    """Shared Redis client, or None (backend not 'redis', or Redis down)."""
    return rate_limit.get_redis()


def _now() -> float:
    return time.time()


def _redis_try_reserve(client, res_id: str, tokens: int, rpm_cap: float, tpm_cap: float) -> float:
    wait_ms = client.eval(
        _RESERVE_LUA, 1, KEY,
        int(_now() * 1000), WINDOW_SECONDS * 1000, tokens, rpm_cap, tpm_cap, res_id,
    )
    return int(wait_ms) / 1000.0


# ---------------------------------------------------------------------------
# In-memory fallback: same rules, one process only.
# ---------------------------------------------------------------------------

_mem_lock = threading.Lock()
_mem_window: list[tuple[float, str, int]] = []  # (timestamp, id, tokens)


def _memory_try_reserve(res_id: str, tokens: int, rpm_cap: float, tpm_cap: float) -> float:
    with _mem_lock:
        now = _now()
        _mem_window[:] = [e for e in _mem_window if now - e[0] < WINDOW_SECONDS]
        used = sum(e[2] for e in _mem_window)
        if len(_mem_window) < rpm_cap and used + tokens <= tpm_cap:
            _mem_window.append((now, res_id, tokens))
            return 0.0
        if not _mem_window:
            return 1.0
        return max(WINDOW_SECONDS - (now - _mem_window[0][0]), 0.001)


def _memory_settle(reservation: Reservation, actual_tokens: int) -> None:
    with _mem_lock:
        for i, (ts, rid, _) in enumerate(_mem_window):
            if rid == reservation.id:
                _mem_window[i] = (ts, rid, actual_tokens)
                return


def reset_memory_window() -> None:
    """For tests."""
    with _mem_lock:
        _mem_window.clear()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def try_reserve(
    tokens: int, rpm_limit: int, tpm_limit: int
) -> tuple[Reservation | None, float]:
    """Non-blocking. Returns (reservation, 0.0) when admitted, or
    (None, seconds_to_wait) when the window is full. Raises TokenBudgetError
    when `tokens` alone is over budget (waiting would never help)."""
    if not fits(tokens, tpm_limit):
        record_quota_event("token_budget_rejected")
        raise TokenBudgetError(
            f"~{tokens} estimated tokens exceeds the {token_budget(tpm_limit):.0f}-token "
            f"per-minute budget (LLM_TPM_LIMIT={tpm_limit})."
        )
    rpm_cap = rpm_limit * SAFETY_FACTOR
    tpm_cap = token_budget(tpm_limit)
    res_id = uuid.uuid4().hex

    client = _redis()
    if client is not None:
        try:
            wait = _redis_try_reserve(client, res_id, tokens, rpm_cap, tpm_cap)
            if wait == 0:
                return Reservation(res_id, tokens, "redis"), 0.0
            return None, wait
        except Exception:
            rate_limit.mark_redis_down()
            record_quota_event("redis_fallback")
            logger.warning("LLM quota: Redis unavailable; using a process-local window.")

    wait = _memory_try_reserve(res_id, tokens, rpm_cap, tpm_cap)
    if wait == 0:
        return Reservation(res_id, tokens, "memory"), 0.0
    return None, wait


def reserve(tokens: int, rpm_limit: int, tpm_limit: int) -> Reservation:
    """Blocking: sleeps until the reservation is admitted. Used by the Celery
    extraction path (which already parks the worker; see _MAX_WAIT_SECONDS)."""
    while True:
        reservation, wait = try_reserve(tokens, rpm_limit, tpm_limit)
        if reservation is not None:
            return reservation
        record_quota_event("wait")
        logger.info("LLM quota: window full -> waiting %.1fs", wait)
        time.sleep(max(wait + 0.5, 1))


def settle(reservation: Reservation, actual_tokens: int) -> None:
    """Replace the reserved estimate with what the call really used."""
    actual_tokens = max(int(actual_tokens), 0)
    if actual_tokens == reservation.tokens:
        return
    if reservation.backend == "redis":
        client = _redis()
        if client is not None:
            try:
                client.eval(
                    _SETTLE_LUA, 1, KEY,
                    f"{reservation.id}:{reservation.tokens}",
                    f"{reservation.id}:{actual_tokens}",
                )
            except Exception:
                rate_limit.mark_redis_down()
                logger.warning("LLM quota: could not settle reservation in Redis.")
        return
    _memory_settle(reservation, actual_tokens)
