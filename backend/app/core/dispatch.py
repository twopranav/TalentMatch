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
import uuid

logger = logging.getLogger(__name__)


def dispatch_extraction(task, entity_id: uuid.UUID | str) -> bool:
    """`task` is a Celery task object (e.g. run_skills_extraction_task)."""
    try:
        task.delay(str(entity_id))
        return True
    except Exception:
        logger.exception(
            "Could not enqueue %s for %s; row stays PENDING and the retry "
            "sweep will re-dispatch it.",
            getattr(task, "name", task), entity_id,
        )
        return False