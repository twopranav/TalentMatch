from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app import models  # noqa: F401
from app.api.routes import health
from app.core.config import settings
from app.api.routes import health, auth, jobs, users, applications, resumes
...

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(applications.router, prefix="/api/applications", tags=["applications"])
app.include_router(resumes.router, prefix="/api/resumes", tags=["resumes"])

@app.get("/")
def root() -> dict:
    return {"app": settings.APP_NAME, "status": "running"}