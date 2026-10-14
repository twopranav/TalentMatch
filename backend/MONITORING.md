# Monitoring TalentMatch (free options)

The backend already exposes everything needed. Nothing here requires code
changes: you only point a free tool at the endpoints below.

## 1. Is it up? (health checks)

| URL | Means | Fails with |
|---|---|---|
| `/api/health` | API process is alive | no response |
| `/api/health/db` | API can reach Postgres | 500 |
| `/api/health/redis` | Redis (broker + rate limits) is reachable | 503 |
| `/api/health/worker` | a Celery worker answers; also reports queue depth | 503 |
| `/api/health/llm` | every task has a real provider/model chosen | **200** with `"status":"error"` |

`/api/health/llm` answers 200 even when something is wrong, so for that one
the checker must look for the text `"status":"ok"` (a keyword monitor), not
just the HTTP status. The same keyword check is harmless on the others.

Suggested monitors: `/api/health`, `/api/health/db`, `/api/health/redis`,
`/api/health/worker`, every 1-5 minutes, alerting by email.
`/api/health/worker` takes up to ~1.5 s (it pings the workers), so don't
poll it faster than once a minute.

### Which tool

* **Uptime Kuma** (free, open source, self-hosted): the safe default for a
  company project, and the only option that works if the API is not on the
  public internet (run it on a machine inside your network).
  `docker run -d --restart=always -p 3001:3001 -v uptime-kuma:/app/data --name uptime-kuma louislam/uptime-kuma:1`
  then open http://localhost:3001, add "HTTP(s) - Keyword" monitors, and an
  email (SMTP) or Teams/Slack notification. Check the project's README for
  the current image tag.
* **UptimeRobot free plan**: easy and hosted, but as of this writing its
  free plan is restricted to personal / non-commercial use. Read their
  terms before using it for Emmvee. It also needs a publicly reachable URL.

## 2. Is it healthy? (metrics)

`GET /metrics` serves Prometheus metrics. In production it returns 404
unless `METRICS_TOKEN` is set; then send `Authorization: Bearer <token>`.
Keep it off the public internet at your reverse proxy as well.

Metrics (all prefixed `talentmatch_`): `http_requests_total{method,route,status}`,
`http_request_duration_seconds`, `task_runs_total{task,state}`,
`task_duration_seconds`, `last_task_finished_timestamp_seconds`,
`queue_depth{queue}`, `stuck_rows{kind}`, `redis_up`.

Free way to see and alert on them: a Prometheus + Grafana pair (both open
source) in Docker, or Grafana Cloud's free tier (needs the API reachable
from the internet, or an agent running next to it). Minimal scrape config:

```yaml
scrape_configs:
  - job_name: talentmatch
    metrics_path: /metrics
    authorization: { credentials: "<METRICS_TOKEN>" }   # sent as Bearer
    static_configs: [{ targets: ["backend:8000"] }]
```

Alerts worth having:

```yaml
groups:
- name: talentmatch
  rules:
  - alert: RedisDown
    expr: talentmatch_redis_up == 0
    for: 2m
  - alert: ExtractionBacklog
    expr: talentmatch_queue_depth{queue="llm"} > 100
    for: 15m
  - alert: RowsStuck          # extractions stuck PENDING, or FAILED out of retries
    expr: sum(talentmatch_stuck_rows) > 0
    for: 30m
  - alert: WorkerNotFinishingTasks
    expr: talentmatch_queue_depth{queue="llm"} > 0 and time() - talentmatch_last_task_finished_timestamp_seconds > 1800
    for: 10m
  - alert: ApiErrors
    expr: sum(rate(talentmatch_http_requests_total{status=~"5.."}[5m])) > 0.1
    for: 5m
  - alert: ApiSlow
    expr: histogram_quantile(0.95, sum by (le) (rate(talentmatch_http_request_duration_seconds_bucket[5m]))) > 5
    for: 10m
```

Caveat: the HTTP metrics live in the API process's memory. The Dockerfile
runs a single uvicorn process, so that's fine. If you ever start uvicorn
with `--workers N`, each scrape hits one random worker and the HTTP numbers
will jump around; set up prometheus_client multiprocess mode first.

## 3. What went wrong? (errors)

Sentry is gone. Errors are in the JSON logs (`LOG_FORMAT=json` in
production): every API request and Celery task shares one `request_id`, and
the same id is returned to clients in the `X-Request-ID` header, so a user
report can be traced from API call to worker task with a single search.
Extractions that fail permanently show up in `stuck_rows`
(`resume_extraction_failed`, `jd_extraction_failed`, `match_scoring_failed`).

## LLM quota metrics

Exported on `/metrics`, written by the worker through Redis like the task metrics:

| Metric | Meaning |
|---|---|
| `talentmatch_llm_quota_events_total{event="wait"}` | An LLM call had to wait for the rolling window to free up. |
| `talentmatch_llm_quota_events_total{event="redis_fallback"}` | Redis was unreachable, so the process-local window was used (quota no longer shared between workers). |
| `talentmatch_llm_quota_events_total{event="token_budget_rejected"}` | A request alone exceeded the per-minute token budget. |
| `talentmatch_llm_quota_tokens_in_window` | Tokens reserved in the last 60 seconds. Compare with `LLM_TPM_LIMIT`. |
| `talentmatch_llm_quota_requests_in_window` | Calls reserved in the last 60 seconds. Compare with `LLM_RPM_LIMIT`. |

A rising `wait` rate with a growing `queue_depth` means the LLM quota, not the worker, is the bottleneck.
