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
import logging
import time

from celery import Celery
from celery.signals import (
    before_task_publish,
    setup_logging,
    task_postrun,
    task_prerun,
)

from app.core.config import settings
from app.core.logging_config import request_id_var, setup_logging as configure_logging
from app.core.metrics import record_task

celery_app = Celery(
    "talentmatch",
    broker=settings.CELERY_BROKER_URL or settings.REDIS_URL,
    backend=settings.CELERY_RESULT_BACKEND or settings.REDIS_URL,
    include=[
        "app.core.skills_extraction_tasks",
        "app.core.jd_skills_extraction_tasks",
        "app.core.extraction_retry_sweep",
        "app.core.matching_tasks",
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
    task_routes={
        "skills_extraction.run": {"queue": settings.LLM_QUEUE_NAME},
        "jd_skills_extraction.run": {"queue": settings.LLM_QUEUE_NAME},
        # Same queue as the extraction tasks so an existing `-Q llm` worker
        # picks scoring up too, and embedding calls share its rate limit.
        "match.score_application": {"queue": settings.LLM_QUEUE_NAME},
    },
    task_annotations={
        name: {
            "soft_time_limit": settings.EXTRACTION_SOFT_TIME_LIMIT,
            "time_limit": settings.EXTRACTION_HARD_TIME_LIMIT,
            **({"rate_limit": settings.LLM_TASK_RATE_LIMIT} if settings.LLM_TASK_RATE_LIMIT else {}),
        }
        for name in ("skills_extraction.run", "jd_skills_extraction.run")
    },
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
        "sweep-unscored-applications": {
            "task": "match.sweep",
            "schedule": 600.0,
        },
    },
)


# ---------------------------------------------------------------------
# Logging and request-id propagation
# ---------------------------------------------------------------------

_task_logger = logging.getLogger("app.task")
_task_started: dict[str, float] = {}


# Connecting any handler to setup_logging stops Celery from installing its
# own root-logger config, so worker and beat use the same JSON/text setup
# as the API.
@setup_logging.connect
def _configure_celery_logging(**_):
    configure_logging("worker")


@before_task_publish.connect
def _attach_request_id(headers=None, **_):
    """Runs in the publisher (the API): copy the current request_id into the
    task message so the worker's logs share it."""
    rid = request_id_var.get()
    if rid and headers is not None:
        headers["request_id"] = rid


@task_prerun.connect
def _task_started_log(task_id=None, task=None, **_):
    rid = getattr(getattr(task, "request", None), "request_id", None)
    request_id_var.set(rid or task_id)
    _task_started[task_id] = time.perf_counter()
    _task_logger.info("task started", extra={"task_name": task.name, "task_id": task_id})


@task_postrun.connect
def _task_finished_log(task_id=None, task=None, state=None, **_):
    started = _task_started.pop(task_id, None)
    _task_logger.info(
        "task finished",
        extra={
            "task_name": task.name,
            "task_id": task_id,
            "state": state,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1) if started else None,
        },
    )
    record_task(
        task.name,
        state or "UNKNOWN",
        (time.perf_counter() - started) if started else None,
    )
    request_id_var.set(None)
