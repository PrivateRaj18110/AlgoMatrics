# Backend

FastAPI service for the Trading Operations Center. Layered, typed, and structured so the in-memory
mock repositories can be swapped for Supabase Postgres without reshaping the API.

## Layering

```
HTTP → routers → services → repositories → mock_data (fixtures)
                         ↘ realtime (broadcaster + publisher)
```

- **Routers** (`app/api/routers/`) — one module per domain; thin, declare `response_model` from
  schemas, raise `HTTPException(404)` on missing ids. Registered in `app/api/router.py`.
- **Schemas** (`app/schemas/`) — Pydantic v2 models mirroring `frontend/src/types`. `common.py` holds
  shared primitives (`TimeSeriesPoint`, `CategoryValue`, `Status`, `Severity`).
- **Repositories** (`app/repositories/`) — the **repository pattern**. `base.InMemoryRepository`
  provides `list()`/`get()`; `__init__.py` instantiates a singleton per domain over `mock_data.py`
  fixtures. `EventsRepository`/`LogsRepository` add `prepend()` for live appends.
- **Services** (`app/services/`) — business logic where it exists: `health_service`,
  `settings_service` (in-memory store), `ingest_service` (SDK → events/logs + broadcast).
- **Realtime** (`app/realtime/`) — `broadcaster.py` (websocket fan-out) and `publisher.py`
  (background loop that jitters telemetry + emits events every ~3s).

## Repository pattern

```python
from app.repositories.base import InMemoryRepository
machines_repo = InMemoryRepository(mock_data.MACHINES)   # list() / get(id)
```

To go live, re-implement these classes against SQLAlchemy (`app/database/session.py` already provides a
lazy engine/session factory). Routers and services don't change — they depend on the repository
interface, not the storage.

## Mock data

`app/repositories/mock_data.py` builds every dataset once at import time from a single seeded
`random.Random(0x5A17)`, so the API is deterministic across requests. The three reference machines
(London VPS, Google Cloud, Personal Computer) and their strategies/brokers/accounts are consistent with
the frontend fixtures.

## Websocket + SDK flow

- Clients connect to `/api/ws`; the `broadcaster` tracks them and the `publisher` streams telemetry.
- The `monitor_sdk` posts to `/api/ingest/*`; `ingest_service` normalises each call into events/logs
  (appended to the repositories) and **broadcasts** them, so an open dashboard reflects live strategy
  activity immediately. See [`SDK_Integration.md`](SDK_Integration.md).

## Run & test

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate     # (source .venv/bin/activate on *nix)
pip install -r requirements.txt
uvicorn main:app --reload                           # http://localhost:8000/docs

pip install -r requirements-dev.txt
pytest -q
```

## Configuration

`app/core/config.py` (pydantic-settings, `.env`): `app_name`, `version`, `environment`, `api_prefix`,
`cors_origins`, and the (blank until Supabase) `database_url`, `supabase_url`, `supabase_anon_key`.

## Adding a domain

1. Add a schema in `app/schemas/`.
2. Add fixtures to `mock_data.py` and a repository singleton in `repositories/__init__.py`.
3. Add a router in `app/api/routers/` and register it in `app/api/router.py`.
