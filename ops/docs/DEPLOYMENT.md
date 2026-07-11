# Deployment

Three independent deployables: **frontend → Vercel**, **backend → Docker**, **database → Supabase**
(when activated).

## Frontend (Vercel)

`frontend/vercel.json` sets the Vite framework, build command and SPA rewrites.

1. Import the repo into Vercel; set the project root to `frontend/`.
2. Build command `npm run build:ci`, output `dist/`.
3. Environment variables:

| Variable             | Value                                   |
| -------------------- | --------------------------------------- |
| `VITE_API_BASE_URL`  | `https://<your-api-host>/api` (omit/empty for mock-only demo) |
| `VITE_USE_MOCK`      | `false` to use the live backend, `true` to force mock |
| `VITE_APP_VERSION`   | e.g. `3.0.0`                            |

A pure-frontend demo needs **no** backend — leave `VITE_API_BASE_URL` empty and it runs on bundled
mock data.

## Backend (Docker)

`backend/Dockerfile` builds a slim, non-root image.

```bash
cd backend
docker build -t raj-quant-os-api .
docker run -p 8000:8000 --env-file .env raj-quant-os-api
# http://localhost:8000/docs
```

Or run directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Backend env (`backend/.env`):

| Variable        | Purpose                                  |
| --------------- | ---------------------------------------- |
| `ENVIRONMENT`   | `production`                             |
| `API_PREFIX`    | `/api`                                   |
| `CORS_ORIGINS`  | comma-separated frontend origins, e.g. `https://app.example.com` |
| `DATABASE_URL`  | Supabase Postgres URL (blank until activated) |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | Supabase project credentials (blank until activated) |

> **CORS / websocket:** add your deployed frontend origin to `CORS_ORIGINS`. The websocket lives at
> `wss://<api-host>/api/ws`; the frontend derives it from `VITE_API_BASE_URL`.

## Database (Supabase) — when activated

1. Provision a Supabase Postgres instance; copy the connection string.
2. Set `DATABASE_URL` (and `SUPABASE_URL` / `SUPABASE_ANON_KEY`).
3. Run Alembic migrations (SQLAlchemy/Alembic scaffolding is already in `backend/`).
4. Re-implement the repositories in `app/repositories/` against SQLAlchemy — routers/services are
   untouched.

## Connecting live strategies

Deploy `monitor_sdk.py` to the three trading projects and point `RAJ_API_BASE` at the backend. See
[`SDK_Integration.md`](SDK_Integration.md).

## Production checklist

- [ ] Frontend env (`VITE_API_BASE_URL`, `VITE_USE_MOCK=false`) set on Vercel
- [ ] Backend `CORS_ORIGINS` includes the deployed frontend origin
- [ ] Backend reachable over HTTPS/WSS
- [ ] (Optional) Supabase provisioned + `DATABASE_URL` set + repositories swapped
- [ ] `monitor_sdk.py` deployed to London VPS / Google Cloud / Personal PC
