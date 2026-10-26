from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401
from app.api.routes import (
    applications,
    audit,
    auth,
    health,
    jobs,
    llm_config,
    metrics,
    recruiter_actions,
    resumes,
    users,
    overview,
)
from app.core.config import settings
from app.core.logging_config import RequestLoggingMiddleware, setup_logging
from app.core.request_limits import BodySizeLimitMiddleware

setup_logging("api")

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG and not settings.IS_PRODUCTION,
    docs_url=None if settings.IS_PRODUCTION else "/docs",
    redoc_url=None if settings.IS_PRODUCTION else "/redoc",
    openapi_url=None if settings.IS_PRODUCTION else "/openapi.json",
)

# Middleware order: the one added LAST is outermost. CORS goes last so that
# even 413/429 error responses carry CORS headers the browser can read.
app.add_middleware(
    BodySizeLimitMiddleware,
    default_limit=settings.MAX_REQUEST_BYTES,
    bulk_limit=settings.MAX_BULK_REQUEST_BYTES,
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if settings.IS_PRODUCTION:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    # The applicants list reports its full (unpaged) size in this header.
    expose_headers=["X-Total-Count", "Retry-After", "X-Request-ID"],
)
# Added last = outermost: every request (even ones rejected by the body-size
# limit or answered by CORS) gets a request_id and one log line.
app.add_middleware(RequestLoggingMiddleware)

app.include_router(health.router, prefix="/api")
app.include_router(metrics.router)  # GET /metrics, see routes/metrics.py
app.include_router(metrics.admin_router, tags=["admin"])  # GET /api/admin/health-metrics
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
# /api/overview (deprecated /api/v1 aliases are mounted at the bottom of this file).
app.include_router(overview.router, prefix="/api", tags=["overview"])  # GET /api/overview
app.include_router(applications.router, prefix="/api/applications", tags=["applications"])
# Notes + manual score share the /api/applications prefix; separate module.
app.include_router(recruiter_actions.router, prefix="/api/applications", tags=["applications"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
app.include_router(resumes.router, prefix="/api/resumes", tags=["resumes"])
app.include_router(llm_config.router, prefix="/api/admin/llm-config", tags=["admin"])


# --- Deprecated /api/v1 aliases -------------------------------------------
# The canonical prefix is /api. /api/v1/... used to be a second mount of the
# same routers; it is kept only so a frontend deployed before this change
# keeps working during a rolling release. Hidden from the OpenAPI docs and
# stamped with a Deprecation header. Delete this block once no client uses it.
def _deprecated_v1(response: Response) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api>; rel="successor-version"'


for _prefix, _router in (
    ("/api/v1", overview.router),
    ("/api/v1/users", users.router),
    ("/api/v1/jobs", jobs.router),
    ("/api/v1/resumes", resumes.router),
):
    app.include_router(
        _router, prefix=_prefix, include_in_schema=False, dependencies=[Depends(_deprecated_v1)]
    )


@app.get("/")
def root() -> dict:
    return {"app": settings.APP_NAME, "status": "running"}