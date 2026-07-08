# Development guide

## Layering

Every bounded context under `backend/src/algo_platform/modules/<context>/`
follows the same four layers, with dependencies pointing inward only:

```text
presentation/   FastAPI routers, request/response schemas — no business rules
application/    use-case services, DTOs, ports, policies
domain/         entities, value objects, domain services — pure Python
infrastructure/ SQLAlchemy models, repositories, vendor clients
```

Enforced rules (see `tests/architecture/test_import_rules.py`):

- `domain/` imports no framework, ORM, transport, or Redis, and never imports
  `application`/`infrastructure`.
- A context does not import another context's `infrastructure` except through the
  consciously whitelisted read-model joins listed in the test.
- Cross-context calls go through public **application facades** (e.g.
  `identity.application.directory.UserDirectory`,
  `billing.application.service.SubscriptionService`), or via versioned integration
  events on the outbox.
- Presentation layers are composition roots: they may wire other contexts'
  application services (that is where dependency injection happens).

## Adding a feature

1. Model the invariant in `domain/` with a frozen value object or an aggregate
   method; add a unit test in `tests/unit`.
2. Add a use case in `application/` that orchestrates repositories/ports.
3. Implement persistence in `infrastructure/` (SQLAlchemy model + repository).
4. Expose it in `presentation/` with a Pydantic-validated router.
5. Register the router in `backend/src/algo_platform/api/app.py`.
6. Add a migration if you changed the schema (`domain` and DB must not drift).
7. Wire the frontend page/hook and add a component test.

## The order path

`OrderService.place_order` is the single guarded write path:

```text
entitlement (plan) → kill switch → pre-trade risk decision (persisted)
 → Order(APPROVED) + outbox events in one transaction
 → engine command on Redis stream
 → PaperExecutionEngine (paper) or LiveRouter (live) fills
 → position projection + cash accounting + WebSocket fan-out
```

Paper fills are deterministic (seeded per order id), so replaying the same order
and tick streams reproduces identical results.

## Tests

- `uv run pytest -m "not integration and not e2e"` — fast, hermetic.
- `uv run pytest -m integration` / `-m e2e` — real PostgreSQL + Redis via
  testcontainers (auto-skips when Docker is unavailable).
- `cd frontend && npm run test` — component/unit tests (Vitest + Testing Library).

## Secrets

- Local: `uv run python scripts/generate_dev_secrets.py` writes `./secrets`
  (git-ignored): RSA JWT keypair + base64 broker KEK.
- Docker: the `secrets-init` Compose service generates them into a shared volume.
- Production: source JWT keys and the broker KEK from a real secret manager; never
  commit them and never place them in `.env`.
