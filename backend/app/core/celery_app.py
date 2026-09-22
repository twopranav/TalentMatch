"""
The single Celery application instance. Import `celery_app` from here
wherever a task needs registering (via @celery_app.task) or dispatching
(via .delay()/.apply_async()) — constructing a second Celery() elsewhere
would register tasks a worker started against *this* instance can't see.

Start a worker with:
    celery -A app.core.celery_app worker --loglevel=info --concurrency=1

Start the beat scheduler (drives the periodic sweep tasks in
extraction_retry_sweep.py -- without this process running, PENDING/
FAILED rows are never automatically retried) separately:
    celery -A app.core.celery_app beat --loglevel=info

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
    include=[
        "app.core.extraction_tasks",
        "app.core.skills_extraction_tasks",
        "app.core.jd_skills_extraction_tasks",
        "app.core.extraction_retry_sweep",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "sweep-stale-resume-skills-extractions": {
            "task": "extraction_retry_sweep.sweep_resumes",
            "schedule": 600.0,  # 10 minutes -- matches STALE_PENDING_AFTER,
                                 # so a row is checked again right as it
                                 # first becomes eligible, not held an
                                 # extra cycle.
        },
        "sweep-stale-job-skills-extractions": {
            "task": "extraction_retry_sweep.sweep_jobs",
            "schedule": 600.0,
        },
    },
)