# Resume Filter Application

Phase 1 skeleton: React frontend + FastAPI backend + PostgreSQL, wired together and deployable.

## Structure

```
backend/
  app/
    core/       # config.py (env settings), security.py (JWT + password hashing)
    db/         # session.py (Postgres/SQLAlchemy engine + Base)
    models/     # SQLAlchemy models (empty — Phase 2 adds User, Job)
    schemas/    # Pydantic request/response schemas (empty — Phase 2 adds them)
    api/routes/ # FastAPI routers (health.py included; Phase 2 adds auth.py, jobs.py)
    main.py     # app entrypoint
  alembic/      # DB migrations
  requirements.txt
  .env.example
frontend/
  src/
    api/client.js  # single axios instance all API calls go through
    App.jsx
    main.jsx
  package.json
.github/workflows/ci.yml   # runs backend migrations + frontend build on every push
```

## Running locally

**Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit DATABASE_URL / JWT_SECRET_KEY
alembic upgrade head   # no-op until Phase 2 adds models + a migration
uvicorn app.main:app --reload
```
Visit http://localhost:8000/api/health and http://localhost:8000/api/health/db to confirm the API and DB connection are both working.

**Frontend**
```bash
cd frontend
npm install
npm run dev
```
Visit http://localhost:5173 — it should show "Backend status: ok" once the backend is running.

## What's deliberately NOT here yet
No auth endpoints, no models, no job/resume features — those are Phase 2+. This phase only proves the skeleton (frontend ↔ backend ↔ Postgres ↔ CI) actually works end to end.
