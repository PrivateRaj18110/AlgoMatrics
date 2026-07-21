# Production infrastructure (Phase 20)

The deployment kit for running Algo Matrics in a Kubernetes cluster, plus the
runtime guardrails that keep a misconfigured production instance from booting.

## Startup self-check (fail-fast)

`create_app` runs a pure production-readiness check
(`shared/application/production_readiness.py`) at boot. In `production` a
**blocking** issue raises and the process refuses to start; elsewhere issues are
logged as warnings. Blocking conditions:

| Code | Condition |
|---|---|
| `cookie_insecure` | `COOKIE_SECURE` is false |
| `cors_wildcard` | `CORS_ORIGINS` contains `*` |
| `cors_plain_http` | a `CORS_ORIGINS` entry is `http://` |
| `security_headers_off` | `SECURITY_HEADERS_ENABLED` is false |
| `rate_limit_off` | `RATE_LIMIT_ENABLED` is false |
| `secrets_env_backend` | `SECRETS_BACKEND` is `env` (use `aws`/`encrypted`) |
| `app_base_url_http` | `APP_BASE_URL` is `http://` |

`metrics_off` is a warning, not blocking.

## Release identity

`GET /api/v1/health/info` returns `{service, version, build_sha, environment}`
(non-sensitive). Set `APP_VERSION` and `BUILD_SHA` from CI at build/deploy time;
the FastAPI OpenAPI version also derives from `APP_VERSION`.

## Kubernetes manifests (`deploy/k8s/`)

Apply in order (numeric prefixes sort correctly):

```
kubectl apply -f deploy/k8s/00-namespace.yaml
kubectl apply -f deploy/k8s/10-config.yaml         # ConfigMap + Secret (populate secrets!)
kubectl apply -f deploy/k8s/15-aicio-storage.yaml  # AI-CIO RWX PVC (set an RWX StorageClass!)
kubectl apply -f deploy/k8s/20-migrate-job.yaml    # alembic upgrade head + seed
kubectl apply -f deploy/k8s/30-api.yaml            # Deployment + Service (health probes)
kubectl apply -f deploy/k8s/40-workers.yaml        # KEDA-scaled event workers
kubectl apply -f deploy/k8s/45-ops.yaml            # ops-api Deployment + Service + Config/Secret
kubectl apply -f deploy/k8s/50-singletons.yaml     # engine / market-data / scheduler (replicas=1)
kubectl apply -f deploy/k8s/55-aicio-pipeline.yaml # AI-CIO daily pipeline (CronJob, sole writer)
kubectl apply -f deploy/k8s/60-ingress.yaml        # API TLS ingress
kubectl apply -f deploy/k8s/65-ops-ingress.yaml    # /ops/api ingress -> ops-api
kubectl apply -f deploy/autoscaling/               # HPA + KEDA ScaledObjects (Phase 19)
```

Key properties:

- **Probes**: liveness → `/health/live`, readiness → `/health/ready` (503 while a
  critical dependency is down, so a sick pod leaves the Service — Phase 18).
- **Singletons**: engine, market-data, scheduler run **one** replica with a
  `Recreate` strategy — they are not horizontally scalable.
- **Workers**: one Deployment per role; `worker-notification` / `worker-trading`
  are the KEDA scale targets (Phase 19). Replicas are managed by KEDA.
- **Migrations**: the `algo-migrate` Job runs `alembic upgrade head` + seed;
  run it before rolling out a new image.
- **Ingress**: preserve the real client IP (e.g. `externalTrafficPolicy: Local`)
  so the org IP allowlist (Phase 17) evaluates the caller, not the ingress.
- **Ops dashboard**: `ops-api` (45) serves the `/ops` backend — live control-plane
  data via an org-scoped read key (`ops-secrets`, `POST /api/v1/api-keys`) with mock
  fallback; **single replica, no HPA** (it holds in-memory telemetry + a websocket).
  `65-ops-ingress.yaml` routes `/ops/api` to it. The **`/ops` SPA static assets and
  the console `/` are served by the frontend** (its own Deployment/Service or a CDN)
  — not part of this kit, same as `60-ingress.yaml`.
- **AI-CIO**: the `algo-aicio-pipeline` CronJob (55) writes the shared DuckDB daily;
  the API + engine mount it **read-only** (an empty/absent file degrades to empty,
  so the platform runs before the first pipeline run). Requires the **ReadWriteMany**
  PVC in `15-aicio-storage.yaml` — set its `storageClassName` to an RWX class
  (EFS / Azure Files / Filestore / NFS / CephFS). Seed the first run:
  `kubectl -n algo create job aicio-init --from=cronjob/algo-aicio-pipeline`.

## Required images

CI (`.github/workflows/ci.yml`, `image` job) builds all four images and, on pushes
to `main`/tags, pushes them to the registry the manifests reference:

| Image | Dockerfile | Used by |
|---|---|---|
| `ghcr.io/algo-matrics/backend` | `deploy/docker/backend.Dockerfile` | api, workers, engine, market-data, scheduler, migrate |
| `ghcr.io/algo-matrics/frontend` | `deploy/docker/frontend.Dockerfile` | console + `/ops` SPA (served externally) |
| `ghcr.io/algo-matrics/ops-api` | `deploy/docker/ops-api.Dockerfile` | `ops-api` |
| `ghcr.io/algo-matrics/aicio` | `deploy/docker/aicio.Dockerfile` | `algo-aicio-pipeline` CronJob |

> Registry auth: `GITHUB_TOKEN` can push only when the repo lives under the
> `algo-matrics` org. If it does not (e.g. a personal fork), set a `GHCR_TOKEN`
> secret (a PAT with `write:packages`) — the login step prefers it — or change the
> `NAMESPACE` in the `image` job **and** the `ghcr.io/algo-matrics/*` refs in
> `deploy/k8s/*` to your own namespace.

## Compose ↔ Kubernetes parity

| Component | Docker Compose | Kubernetes | Difference |
|---|---|---|---|
| Backend API | `api` | `30-api.yaml` (Deploy+Svc, 2 replicas, HPA) | — |
| Frontend | `frontend` (nginx serves `/` + `/ops`) | external (CDN / own Deploy) | **Not in kit** (by design — see 60-ingress) |
| Engine | `trading-engine` | `50-singletons` `algo-engine` (1, Recreate) | — |
| Market data | `market-data` | `50-singletons` `algo-market-data` (1) | — |
| Scheduler | `scheduler` | `50-singletons` `algo-scheduler` (1) | — |
| Workers | `worker` (all roles) | `40-workers` per-role + KEDA | k8s splits roles for scaling |
| AI-CIO | `aicio-pipeline` (loop, RW vol) | `55-aicio-pipeline` CronJob + `15` RWX PVC | k8s CronJob; needs RWX |
| Ops API | `ops-api` | `45-ops.yaml` (Deploy+Svc, 1, no HPA) | — |
| Shared storage | named volume `aicio_data` | `15` RWX PVC `algo-aicio-data` | needs an RWX StorageClass |
| Postgres / Redis | `postgres`, `redis` | external (managed) | **Not in kit** (managed DB/cache) |
| Monitoring | `docker-compose.observability.yml` | separate (Helm/operators) + `deploy/autoscaling` | separate in both |
| Logging | structured stdout | structured stdout | aggregation separate in both |
| Health checks | compose `healthcheck` (api, ops-api) | liveness/readiness probes (api, ops-api) | — (non-HTTP procs: none in both) |
| Networking | one nginx routes `/`,`/api`,`/ops`,`/ops/api` | ingress-nginx `60` (api) + `65` (/ops/api); `/`+`/ops` via frontend | frontend routing external in k8s |
| Secrets | `.env` + `secrets-init` (JWT/KEK gen) | `algo-secrets` / `ops-secrets` (external secret mgr) | JWT/KEK must be provided, not generated |
| CI/CD | `compose up --build` (local) | CI builds + pushes 4 images to GHCR | wired in this change |

## Deploy sequence (per release)

1. Build + push the images (CI does this on `main`/tags: backend, frontend,
   ops-api, aicio -> `ghcr.io/algo-matrics/*`), tagged with the git SHA; set
   `APP_VERSION`/`BUILD_SHA`.
2. Run the migrate Job; confirm it completes.
3. Roll out API + workers + singletons (`kubectl set image` / Helm).
4. Verify `GET /health/info` reports the new `build_sha` and `/health/ready` is
   `200` on new pods; watch error rate / latency dashboards (Phase 1).
5. Roll back by redeploying the previous image tag. Migrations are expand/
   contract, so the prior image runs against the new schema.

## Production readiness checklist

- [ ] `APP_ENV=production`, and the startup self-check passes (no blocking log).
- [ ] Secrets in a real backend (`SECRETS_BACKEND=aws`/`encrypted`), not `env`.
- [ ] TLS at the ingress; `COOKIE_SECURE=true`; `CORS_ORIGINS` = your https app.
- [ ] Managed Postgres + Redis (7+) with backups and failover.
- [ ] Metrics/logs shipping (Phase 1 stack) and alerts wired.
- [ ] HPA + KEDA applied; `SCALING_MAX_REPLICAS` matches KEDA `maxReplicaCount`.
- [ ] Migrate Job runs in CI/CD before rollout.
- [ ] All four images pushed to `ghcr.io/algo-matrics/{backend,frontend,ops-api,aicio}`
      (CI push creds set — see *Required images*).
- [ ] AI-CIO PVC bound: an **RWX** `storageClassName` set in `15-aicio-storage.yaml`.
- [ ] Ops read key set (`ALGOMATRICS_API_KEY` + `ALGOMATRICS_ORG_ID` in `ops-secrets`),
      else `/ops` serves mock.
- [ ] Frontend deployed at the app host (serves `/` + `/ops` static); `/ops/api`
      resolves to `ops-ingress`.
- [ ] AI-CIO seeded once:
      `kubectl -n algo create job aicio-init --from=cronjob/algo-aicio-pipeline`.

## Rollback

- **App / config**: `kubectl -n algo rollout undo deployment/<name>` (any of
  `algo-api`, `ops-api`, `worker-notification`, `worker-trading`, `algo-engine`,
  `algo-market-data`, `algo-scheduler`), or redeploy the previous SHA-tagged image
  (`kubectl -n algo set image deployment/algo-api api=ghcr.io/algo-matrics/backend:<sha>`).
  Migrations are expand/contract, so the prior image runs against the new schema.
- **AI-CIO / ops (additive)**: remove without touching the core platform —
  `kubectl delete -f deploy/k8s/65-ops-ingress.yaml -f deploy/k8s/55-aicio-pipeline.yaml -f deploy/k8s/45-ops.yaml`.
  To also drop the shared storage, delete `15-aicio-storage.yaml` **and** remove the
  `aicio-data` volume blocks from `30-api.yaml` / `50-singletons.yaml` (otherwise
  those pods stay `Pending`).
- **Images**: pin the k8s manifests to a known-good SHA tag instead of `latest` to
  make image rollbacks explicit and repeatable.
