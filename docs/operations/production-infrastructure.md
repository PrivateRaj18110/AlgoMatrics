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
kubectl apply -f deploy/k8s/10-config.yaml     # ConfigMap + Secret (populate secrets!)
kubectl apply -f deploy/k8s/20-migrate-job.yaml  # alembic upgrade head + seed
kubectl apply -f deploy/k8s/30-api.yaml        # Deployment + Service (health probes)
kubectl apply -f deploy/k8s/40-workers.yaml    # KEDA-scaled event workers
kubectl apply -f deploy/k8s/50-singletons.yaml # engine / market-data / scheduler (replicas=1)
kubectl apply -f deploy/k8s/60-ingress.yaml    # TLS ingress
kubectl apply -f deploy/autoscaling/           # HPA + KEDA ScaledObjects (Phase 19)
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

## Deploy sequence (per release)

1. Build + push the image, tagged with the git SHA; set `APP_VERSION`/`BUILD_SHA`.
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

## Rollback

All additive: pure self-check + one endpoint + YAML manifests, no migration.
Revert the `phase-20-production-infrastructure` branch to remove the code; delete
the manifests to tear down the deployment.
