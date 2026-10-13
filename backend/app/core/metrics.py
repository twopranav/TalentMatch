"""
Prometheus metrics, all served from the API's GET /metrics.

Why everything is read in the API process: the Celery worker runs tasks in
a forked child process, so ordinary in-process counters there are awkward
to scrape. Instead the worker writes tiny counters into Redis (record_task,
called from Celery signals) and a collector here reads them at scrape time,
together with queue lengths and a count of rows stuck in extraction.

Metrics (all prefixed talentmatch_):
  http_requests_total{method,route,status}      requests, by route TEMPLATE
  http_request_duration_seconds{method,route}   latency histogram
  task_runs_total{task,state}                   finished Celery tasks
  task_duration_seconds{task}                   summary (count + sum)
  last_task_finished_timestamp_seconds          proves worker + beat are alive
  queue_depth{queue}                            messages waiting in Redis
  stuck_rows{kind}                              rows needing attention
  redis_up                                      1 if Redis answered

Labels are always bounded: routes use the path template ("/jobs/{job_id}"),
never the raw URL, and no user, email or file data is ever a label.
"""
import logging
import time

from prometheus_client import Counter, Histogram
from prometheus_client.core import GaugeMetricFamily, REGISTRY, SummaryMetricFamily, CounterMetricFamily

from app.core.config import settings

logger = logging.getLogger(__name__)

_TASK_COUNT_KEY = "tm:metrics:task_count"          # hash "task|STATE" -> n
_TASK_DURATION_SUM_KEY = "tm:metrics:task_dur_sum"  # hash task -> seconds
_TASK_DURATION_N_KEY = "tm:metrics:task_dur_n"      # hash task -> n
_LAST_FINISHED_KEY = "tm:metrics:last_task_finished"

HTTP_REQUESTS = Counter(
    "talentmatch_http_requests_total",
    "HTTP requests handled by the API.",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "talentmatch_http_request_duration_seconds",
    "HTTP request latency.",
    ["method", "route"],
    buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)

_redis_client = None


def _redis():
    """Short-timeout Redis client (a slow Redis must not hang a scrape)."""
    global _redis_client
    if _redis_client is None:
        import redis

        _redis_client = redis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1
        )
    return _redis_client


def route_template(scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


def observe_request(method: str, route: str, status: int, seconds: float) -> None:
    HTTP_REQUESTS.labels(method, route, str(status)).inc()
    HTTP_DURATION.labels(method, route).observe(seconds)


# ---------------------------------------------------------------------
# Worker side: called from Celery signals (see celery_app.py)
# ---------------------------------------------------------------------


def record_task(task: str, state: str, seconds: float | None) -> None:
    """Never raises: metrics must not be able to fail a task."""
    try:
        r = _redis()
        pipe = r.pipeline()
        pipe.hincrby(_TASK_COUNT_KEY, f"{task}|{state}", 1)
        if seconds is not None:
            pipe.hincrbyfloat(_TASK_DURATION_SUM_KEY, task, seconds)
            pipe.hincrby(_TASK_DURATION_N_KEY, task, 1)
        pipe.set(_LAST_FINISHED_KEY, time.time())
        pipe.execute()
    except Exception:
        logger.debug("could not record task metric", exc_info=True)


# ---------------------------------------------------------------------
# Scrape side
# ---------------------------------------------------------------------

_stuck_cache: tuple[float, dict[str, int]] | None = None
_STUCK_CACHE_SECONDS = 30
_STUCK_PENDING_AFTER_MINUTES = 30


def _count_stuck_rows() -> dict[str, int]:
    """Rows a person (or the sweep) needs to look at. Cached for 30s so a
    15s scrape interval doesn't hit Postgres every time."""
    global _stuck_cache
    now = time.monotonic()
    if _stuck_cache and now - _stuck_cache[0] < _STUCK_CACHE_SECONDS:
        return _stuck_cache[1]

    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, select

    from app.core.extraction_retry_sweep import MAX_AUTO_RETRIES
    from app.db.session import SessionLocal
    from app.models.application import Application
    from app.models.job import Job, JobExtractionStatus
    from app.models.resume import Resume, ResumeExtractionStatus

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=_STUCK_PENDING_AFTER_MINUTES)
    db = SessionLocal()
    try:
        def count(stmt) -> int:
            return int(db.scalar(stmt) or 0)

        result = {
            # Still PENDING long after the sweep (10 min) should have fixed it.
            "resume_extraction_pending": count(
                select(func.count()).select_from(Resume).where(
                    Resume.skills_extraction_status == ResumeExtractionStatus.PENDING,
                    Resume.updated_at < cutoff,
                )
            ),
            "jd_extraction_pending": count(
                select(func.count()).select_from(Job).where(
                    Job.skills_extraction_status == JobExtractionStatus.PENDING,
                    Job.updated_at < cutoff,
                    Job.jd_raw_text.is_not(None),
                )
            ),
            # FAILED and out of automatic retries: needs a human.
            "resume_extraction_failed": count(
                select(func.count()).select_from(Resume).where(
                    Resume.skills_extraction_status == ResumeExtractionStatus.FAILED,
                    Resume.skills_extraction_retry_count >= MAX_AUTO_RETRIES,
                )
            ),
            "jd_extraction_failed": count(
                select(func.count()).select_from(Job).where(
                    Job.skills_extraction_status == JobExtractionStatus.FAILED,
                    Job.skills_extraction_retry_count >= MAX_AUTO_RETRIES,
                )
            ),
            "match_scoring_failed": count(
                select(func.count()).select_from(Application).where(
                    Application.match_status == "failed"
                )
            ),
        }
    finally:
        db.close()

    _stuck_cache = (now, result)
    return result


def queue_names() -> list[str]:
    # "celery" is the default queue the periodic sweeps run on.
    return sorted({settings.LLM_QUEUE_NAME, "celery"})


class _AppCollector:
    """Reads Redis/Postgres at scrape time. Any failure degrades to
    redis_up=0 / missing series rather than breaking /metrics."""

    def collect(self):
        redis_up = GaugeMetricFamily("talentmatch_redis_up", "1 if Redis answered.")
        queue = GaugeMetricFamily(
            "talentmatch_queue_depth", "Messages waiting in a Celery queue.", labels=["queue"]
        )
        runs = CounterMetricFamily(
            "talentmatch_task_runs", "Finished Celery tasks.", labels=["task", "state"]
        )
        durations = SummaryMetricFamily(
            "talentmatch_task_duration_seconds", "Celery task run time.", labels=["task"]
        )
        last = GaugeMetricFamily(
            "talentmatch_last_task_finished_timestamp_seconds",
            "Unix time the worker last finished any task (0 = never).",
        )

        try:
            r = _redis()
            r.ping()
            redis_up.add_metric([], 1)

            for name in queue_names():
                queue.add_metric([name], float(r.llen(name)))

            for field, value in r.hgetall(_TASK_COUNT_KEY).items():
                task, _, state = field.decode().partition("|")
                runs.add_metric([task, state], float(value))

            sums = {k.decode(): float(v) for k, v in r.hgetall(_TASK_DURATION_SUM_KEY).items()}
            counts = {k.decode(): int(v) for k, v in r.hgetall(_TASK_DURATION_N_KEY).items()}
            for task, n in counts.items():
                durations.add_metric([task], n, sums.get(task, 0.0))

            raw = r.get(_LAST_FINISHED_KEY)
            last.add_metric([], float(raw) if raw else 0.0)
        except Exception:
            redis_up.add_metric([], 0)
            logger.debug("redis metrics unavailable", exc_info=True)

        yield redis_up
        yield queue
        yield runs
        yield durations
        yield last

        stuck = GaugeMetricFamily(
            "talentmatch_stuck_rows", "Rows needing attention.", labels=["kind"]
        )
        try:
            for kind, n in _count_stuck_rows().items():
                stuck.add_metric([kind], n)
        except Exception:
            logger.debug("stuck-row metrics unavailable", exc_info=True)
        yield stuck


_collector_registered = False


def register_collector() -> None:
    global _collector_registered
    if not _collector_registered:
        REGISTRY.register(_AppCollector())
        _collector_registered = True
