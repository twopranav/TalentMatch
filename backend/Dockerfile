# Build context is the REPO ROOT (see docker-compose.yml's
# `context: .` for this service) — not this backend/ folder — because
# requirements.txt sits at the repo root while this Dockerfile and the
# app code it packages live under backend/. COPY paths below are
# therefore relative to the repo root, not to this file's location.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only the backend/ subtree -- .dockerignore at the repo root keeps
# frontend/, scripts/, testing files/, backend/storage/ (local resume
# blobs — real candidate PII, must never end up baked into an image
# layer) and backend/.env (secrets — passed in at runtime instead) out
# of this entirely.
COPY backend/ .

EXPOSE 8000

# docker-compose overrides this CMD for the worker service.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]