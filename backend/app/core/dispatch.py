"""
Single choke point for putting an extraction job on the queue.

Every upload route calls dispatch_extraction() AFTER its DB commit. If
the broker (Redis) is down at that moment, the upload has already
succeeded and the row is sitting at PENDING -- so we log loudly and
return False instead of turning a stored file into a 500. The beat
sweep (extraction_retry_sweep.py) re-queues PENDING rows that are still
untouched after STALE_PENDING_AFTER, so nothing is lost.
"""

import logging
import time
import uuid

from app.core import rate_limit
from app.core.config import settings

logger = logging.getLogger(__name__)

# In-process fallback for acquire_once() when Redis is unavailable.
_once_until: dict[str, float] = {}


def acquire_once(key: str, ttl_seconds: int) -> bool:
    """Dedupe lock: True the first time `key` is seen inside `ttl_seconds`,
    False for repeats. Redis `SET key 1 NX EX ttl` is atomic, so two
    simultaneous requests can't both win. Falls back to a per-process dict
    if Redis is down, and always returns True when the limiter backend is
    "off" (tests) so unrelated tests never see stale locks."""
    if settings.RATE_LIMIT_BACKEND == "off":
        return True
    client = rate_limit.get_redis()
    if client is not None:
        try:
            return bool(client.set(f"once:{key}", 1, nx=True, ex=ttl_seconds))
        except Exception:
            rate_limit.mark_redis_down()
    now = time.monotonic()
    if _once_until.get(key, 0.0) > now:
        return False
    _once_until[key] = now + ttl_seconds
    return True


def dispatch_extraction(
    task, entity_id: uuid.UUID | str, countdown: int | None = None
) -> bool:
    """`task` is a Celery task object (e.g. run_skills_extraction_task).
    `countdown` (seconds) delays the start; used to stagger big fan-outs."""
    try:
        if countdown:
            task.apply_async(args=[str(entity_id)], countdown=countdown)
        else:
            task.delay(str(entity_id))
        return True
    except Exception:
        logger.exception(
            "Could not enqueue %s for %s; row stays PENDING and the retry "
            "sweep will re-dispatch it.",
            getattr(task, "name", task), entity_id,
        )
        return False