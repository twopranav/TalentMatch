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
  llm_quota_events_total{event}                 wait | redis_fallback | token_budget_rejected
  llm_quota_tokens_in_window                    tokens reserved in the rolling 60s window
  llm_quota_requests_in_window                  LLM calls reserved in the rolling 60s window

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
_QUOTA_EVENTS_KEY = "tm:metrics:quota_events"       # hash event -> n

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


def record_quota_event(event: str) -> None:
    """Count an LLM-quota event (called from the worker, via llm_quota).
    Never raises, and does nothing unless the shared Redis backend is on,
    so tests and single-process dev runs pay no connection timeout."""
    if settings.RATE_LIMIT_BACKEND != "redis":
        return
    try:
        _redis().hincrby(_QUOTA_EVENTS_KEY, event, 1)
    except Exception:
        logger.debug("could not record quota event", exc_info=True)


def _quota_window_usage(r) -> tuple[int, int]:
    """(tokens, requests) currently reserved in the shared LLM quota window.
    Members of the sorted set look like "<id>:<tokens>", scored by time in ms."""
    from app.core import llm_quota

    now_ms = int(time.time() * 1000)
    members = r.zrangebyscore(
        llm_quota.KEY, now_ms - llm_quota.WINDOW_SECONDS * 1000, "+inf"
    )
    tokens = 0
    for m in members:
        text = m.decode() if isinstance(m, bytes) else str(m)
        tokens += int(text.rsplit(":", 1)[-1])
    return tokens, len(members)


# ---------------------------------------------------------------------
# Scrape side
# ---------------------------------------------------------------------

_stuck_cache: tuple[float, dict[str, int]] | None = None
_STUCK_CACHE_SECONDS = 30
_STUCK_PENDING_AFTER_MINUTES = 30


def _count_stuck_rows(use_cache: bool = True) -> dict[str, int]:
    """Rows a person (or the sweep) needs to look at. Cached for 30s so a
    15s scrape interval doesn't hit Postgres every time."""
    global _stuck_cache
    now = time.monotonic()
    if use_cache and _stuck_cache and now - _stuck_cache[0] < _STUCK_CACHE_SECONDS:
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

        # Quota series live in their own try block: a problem reading them
        # must not flip redis_up to 0 or hide the series above.
        quota_events = CounterMetricFamily(
            "talentmatch_llm_quota_events",
            "LLM quota events (waits, Redis fallbacks, over-budget rejections).",
            labels=["event"],
        )
        quota_tokens = GaugeMetricFamily(
            "talentmatch_llm_quota_tokens_in_window",
            "Tokens reserved in the rolling LLM quota window.",
        )
        quota_requests = GaugeMetricFamily(
            "talentmatch_llm_quota_requests_in_window",
            "LLM calls reserved in the rolling LLM quota window.",
        )
        try:
            r = _redis()
            for field, value in r.hgetall(_QUOTA_EVENTS_KEY).items():
                quota_events.add_metric([field.decode()], float(value))
            tokens, requests_n = _quota_window_usage(r)
            quota_tokens.add_metric([], tokens)
            quota_requests.add_metric([], requests_n)
        except Exception:
            logger.debug("llm quota metrics unavailable", exc_info=True)
        yield quota_events
        yield quota_tokens
        yield quota_requests

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


# ---------------------------------------------------------------------
# Snapshot helpers shared by GET /api/v1/overview (admin) and
# GET /api/v1/admin/health-metrics. Every one of them degrades to a
# harmless value instead of raising: a dashboard must not 500 because
# Redis is down.
# ---------------------------------------------------------------------

_PROBE_KEY = "tm:metrics:llm_probe"  # hash task -> JSON of the last probe
_probe_memory: dict[str, dict] = {}   # single-process fallback / test mode


def redis_status() -> str:
    """"ok" | "unavailable" | "disabled" (RATE_LIMIT_BACKEND is not redis)."""
    if settings.RATE_LIMIT_BACKEND != "redis":
        return "disabled"
    from app.core import rate_limit

    client = rate_limit.get_redis()
    if client is None:
        return "unavailable"
    try:
        client.ping()
        return "ok"
    except Exception:
        rate_limit.mark_redis_down()
        return "unavailable"


def queue_depths() -> dict | None:
    """{"queues": {name: n}, "total": n}, or None when Redis can't be read."""
    from app.core import rate_limit

    client = rate_limit.get_redis()
    if client is None:
        return None
    try:
        queues = {name: int(client.llen(name)) for name in queue_names()}
    except Exception:
        rate_limit.mark_redis_down()
        return None
    return {"queues": queues, "total": sum(queues.values())}


def quota_snapshot() -> dict:
    """Usage of the shared rolling LLM quota window (Redis, or this
    process's memory window when Redis is not in use)."""
    from app.core import llm_quota, rate_limit

    snap = {
        "backend": "memory",
        "window_seconds": llm_quota.WINDOW_SECONDS,
        "tokens_in_window": 0,
        "requests_in_window": 0,
        "tpm_limit": settings.LLM_TPM_LIMIT,
        "rpm_limit": settings.LLM_RPM_LIMIT,
        "token_budget": llm_quota.token_budget(settings.LLM_TPM_LIMIT),
    }
    client = rate_limit.get_redis()
    if client is not None:
        try:
            tokens, requests_n = _quota_window_usage(client)
            snap.update(backend="redis", tokens_in_window=tokens, requests_in_window=requests_n)
            return snap
        except Exception:
            logger.debug("quota snapshot: redis unreadable, using memory window", exc_info=True)
    with llm_quota._mem_lock:
        now = time.time()
        live = [x for x in llm_quota._mem_window if now - x[0] < llm_quota.WINDOW_SECONDS]
    snap.update(tokens_in_window=sum(x[2] for x in live), requests_in_window=len(live))
    return snap


def record_probe_result(task: str, result: dict) -> None:
    """Remember the outcome of the last /llm-config/{task}/probe. Never raises."""
    import json
    from datetime import datetime, timezone

    ok = bool(result.get("ok"))
    error = result.get("error")
    entry = {
        "ok": ok,
        "stage": result.get("stage") or ("ok" if ok else None),
        "error": str(error)[:300] if error else None,
        "elapsed_s": result.get("elapsed_s"),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    _probe_memory[task] = entry
    if settings.RATE_LIMIT_BACKEND != "redis":
        return
    try:
        from app.core import rate_limit

        client = rate_limit.get_redis()
        if client is not None:
            client.hset(_PROBE_KEY, task, json.dumps(entry))
    except Exception:
        logger.debug("could not store probe result", exc_info=True)


def last_probe_results() -> dict[str, dict]:
    import json

    results = dict(_probe_memory)
    if settings.RATE_LIMIT_BACKEND == "redis":
        try:
            from app.core import rate_limit

            client = rate_limit.get_redis()
            if client is not None:
                for field, value in client.hgetall(_PROBE_KEY).items():
                    key = field.decode() if isinstance(field, bytes) else str(field)
                    results[key] = json.loads(value)
        except Exception:
            logger.debug("could not read probe results", exc_info=True)
    return results
