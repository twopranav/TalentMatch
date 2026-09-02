from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health
from app.core.config import settings

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")

# Phase 2 will add: app.include_router(auth.router, prefix="/api/auth")
# Phase 2 will add: app.include_router(jobs.router, prefix="/api/jobs")


@app.get("/")
def root() -> dict:
    return {"app": settings.APP_NAME, "status": "running"}
