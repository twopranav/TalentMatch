"""Shared rate limiting (Redis-backed, in-memory fallback)."""
import logging
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)

_memory_hits: dict[str, deque] = defaultdict(deque)
_redis_client = None
_redis_down_until = 0.0
_REDIS_RETRY_SECONDS = 30


def get_redis():
    """Shared Redis client, or None when the backend isn't 'redis' or Redis
    was unreachable very recently."""
    global _redis_client
    if settings.RATE_LIMIT_BACKEND != "redis" or time.monotonic() < _redis_down_until:
        return None
    if _redis_client is None:
        import redis

        _redis_client = redis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=0.25, socket_timeout=0.25
        )
    return _redis_client


def mark_redis_down() -> None:
    global _redis_down_until
    _redis_down_until = time.monotonic() + _REDIS_RETRY_SECONDS
    logger.warning("Redis unreachable for rate limiting; using in-memory counters for %ss", _REDIS_RETRY_SECONDS)


def hit(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Counts one hit. Returns (allowed, retry_after_seconds)."""
    if settings.RATE_LIMIT_BACKEND == "off":
        return True, 0
    client = get_redis()
    if client is not None:
        try:
            now = time.time()
            bucket = int(now // window_seconds)
            rkey = f"rl:{key}:{bucket}"
            pipe = client.pipeline()
            pipe.incr(rkey)
            pipe.expire(rkey, window_seconds)
            count = pipe.execute()[0]
            return count <= limit, window_seconds - int(now % window_seconds)
        except Exception:
            mark_redis_down()
    now = time.monotonic()
    hits = _memory_hits[key]
    while hits and hits[0] <= now - window_seconds:
        hits.popleft()
    if len(hits) >= limit:
        return False, int(window_seconds - (now - hits[0])) + 1
    hits.append(now)
    return True, 0


def enforce(key: str, limit: int, window_seconds: int) -> None:
    allowed, retry_after = hit(key, limit, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many requests. Try again in {retry_after} second(s).",
            headers={"Retry-After": str(retry_after)},
        )


def limit_by_ip(name: str, limit: int, window_seconds: int):
    """FastAPI dependency: limit per client IP. Behind a reverse proxy, run
    uvicorn with --proxy-headers so request.client is the real client."""
    def checker(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        enforce(f"{name}:ip:{ip}", limit, window_seconds)
    return checker