# Build context is the REPO ROOT (see docker-compose.yml's
# `context: .` for this service) — not this backend/ folder — because
# requirements.txt sits at the repo root while this Dockerfile and the
# app code it packages live under backend/. COPY paths below are
# therefore relative to the repo root, not to this file's location.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

# Install CPU-only torch first so sentence-transformers doesn't pull the
# multi-GB GPU build from PyPI. The next step sees torch is already there.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Local embedding model, exported once to models/all-MiniLM-L6-v2 and copied
# in, so neither the build nor the containers contact Hugging Face.
# Must match EMBEDDING_MODEL in .env (/opt/models/all-MiniLM-L6-v2).
ENV HF_HUB_OFFLINE=1
COPY models/all-MiniLM-L6-v2 /opt/models/all-MiniLM-L6-v2
# Fails the build if the exported model is incomplete.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('/opt/models/all-MiniLM-L6-v2')"

# Only the backend/ subtree -- .dockerignore at the repo root keeps
# frontend/, scripts/, testing files/, backend/storage/ (local resume
# blobs — real candidate PII, must never end up baked into an image
# layer) and backend/.env (secrets — passed in at runtime instead) out
# of this entirely.
COPY backend/ .

EXPOSE 8000

# docker-compose overrides this CMD for the worker service.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]