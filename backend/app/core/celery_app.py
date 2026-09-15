"""
The single Celery application instance. Import `celery_app` from here
wherever a task needs registering (via @celery_app.task) or dispatching
(via .delay()/.apply_async()) — constructing a second Celery() elsewhere
would register tasks a worker started against *this* instance can't see.

Start a worker with:
    celery -A app.core.celery_app worker --loglevel=info --concurrency=1

--concurrency=1 is deliberate for now: it caps HF API calls to one in
flight at a time, network-wide, regardless of how many resumes are
queued — the whole point of moving extraction behind a queue in the
first place. Raise it later once you know your actual free-tier
rate limit and want more throughput.

Redis serves double duty: message broker (carries the task message from
the FastAPI process to a worker) and result backend (stores task
state/return value). Fine at this scale — one moving part instead of two.
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "talentmatch",
    broker=settings.CELERY_BROKER_URL or settings.REDIS_URL,
    backend=settings.CELERY_RESULT_BACKEND or settings.REDIS_URL,
    include=["app.core.extraction_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)