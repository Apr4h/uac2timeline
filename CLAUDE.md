# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

`uac2timeline` parses [UAC (Unix Artifacts Collector)](https://github.com/tclahr/uac) forensic collection directories and exposes parsed artifacts through a web UI. Analysts upload ZIP/tar.gz archives of UAC collections, background workers parse each artifact type, and a Vue frontend presents a filterable timeline view.

## Architecture

```
┌───────────────────────────────┐
│      Vue 3 + Vite (frontend/) │  http://localhost:5173
└──────────────┬────────────────┘
               │ /api  (proxied in dev)
┌──────────────▼────────────────┐
│    FastAPI   (backend/app/)   │  http://localhost:8000
└──────┬───────────────┬────────┘
       │               │
   SQLite (uac.db)  Redis broker
       │               │
       │  ┌────────────▼────────────┐
       └──│   Celery workers        │
          │  (per-artifact tasks)   │
          └─────────────────────────┘
```

**Two Python packages:**
- `uac_parser/` — original parsing library (unchanged); all parsers return plain lists of ORM objects
- `backend/app/` — FastAPI application, Celery tasks, job-tracking models

**SQLAlchemy Base** is declared in `uac_parser/database.py`. All models (both `uac_parser/models.py` and `backend/app/models.py`) import that same `Base`, so `Base.metadata.create_all()` creates every table.

## Development setup

```bash
# Terminal 1: Redis
docker run -p 6379:6379 redis:alpine

# Terminal 2: FastAPI  (run from repo root so both packages are importable)
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000

# Terminal 3: Celery worker
celery -A backend.app.tasks.celery_app worker --loglevel=info

# Terminal 4: Vite dev server  (proxies /api → :8000)
cd frontend && npm install && npm run dev
```

## Docker (full stack)

```bash
docker-compose up --build
# UI at http://localhost:5173  |  API at http://localhost:8000
```

## Key file map

| Path | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI app factory; mounts routers; serves `frontend/dist` in prod |
| `backend/app/config.py` | `DB_PATH`, `REDIS_URL`, `UPLOAD_DIR`, `PARSE_THRESHOLD` (env-overridable) |
| `backend/app/database.py` | `engine()` singleton, `get_db()` FastAPI dependency, table creation |
| `backend/app/models.py` | `ProcessingJob`, `ArtifactJob`, `ProcessingLog` ORM models |
| `backend/app/schemas.py` | Pydantic response schemas for all API endpoints |
| `backend/app/api/collections.py` | Upload, CRUD, and job endpoints |
| `backend/app/api/timeline.py` | Unified timeline + per-artifact query endpoints |
| `backend/app/tasks/celery_app.py` | Celery instance (broker = Redis) |
| `backend/app/tasks/parsers.py` | `process_collection` orchestrator + 5 per-artifact Celery tasks |
| `uac_parser/` | Parsing library — leave imports as `uac_parser.*` |
| `frontend/src/stores/collections.js` | Pinia: collection list, upload, delete, job polling |
| `frontend/src/stores/timeline.js` | Pinia: filter state, timeline data, per-artifact fetch |
| `frontend/src/views/CollectionsView.vue` | Collection grid + upload dialog |
| `frontend/src/views/AnalysisView.vue` | Tabbed analysis: Timeline / Processes / Network / Auth / Commands / Users |

## Upload & processing flow

1. `POST /api/collections/upload` — saves archive, extracts it, reads `uac.log` metadata, creates `UACCollection` + `ProcessingJob` in DB, dispatches `process_collection` Celery task
2. `process_collection` — creates one `ArtifactJob` per artifact type, dispatches a Celery `chord(group(subtasks))(finalize_collection)`
3. Each subtask — updates `ArtifactJob`, runs the corresponding `uac_parser.artifacts.*` parser, bulk-inserts results, saves captured log records to `ProcessingLog`
4. Frontend polls `GET /api/collections/{id}` every 2 s while a job is `pending`/`running`

## Timeline API

`GET /api/collections/{id}/timeline` performs a Python-level UNION across `processes`, `authentications`, and `command_history` (all have timestamps). Network connections have no timestamp and appear only when no date range filter is active. Query params: `start`, `end`, `types`, `filter` (substring), `regex`, `limit`, `offset`.

## Adding a new artifact type

1. Add parser in `uac_parser/artifacts/<type>.py` following the existing pattern (return `list[ORM objects]`)
2. Add ORM model to `uac_parser/models.py`
3. Add `relationship` to `UACCollection`
4. Add a new `@celery.task` in `backend/app/tasks/parsers.py` and register it in `ARTIFACT_TASKS`
5. Add Pydantic schema in `backend/app/schemas.py`
6. Add endpoint in `backend/app/api/timeline.py`
7. Wire up a new tab in `frontend/src/views/AnalysisView.vue`

## Test data

```bash
# Create an archive from a test collection and upload via the UI
zip -r /tmp/ubuntu_vm.zip test_data/ubuntu_vm
zip -r /tmp/mac.zip test_data/mac
```
