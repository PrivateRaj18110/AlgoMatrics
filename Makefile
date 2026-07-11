.PHONY: install dev-secrets lint format typecheck test test-integration test-e2e \
        frontend-install frontend-build frontend-test frontend-lint \
        ops-frontend-install ops-frontend-build ops-backend-test \
        compose-up compose-down compose-logs migrate seed verify

install:
	uv sync --all-groups

dev-secrets:
	uv run python scripts/generate_dev_secrets.py

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy backend/src packages agents

test:
	uv run pytest -m "not integration and not e2e"

test-integration:
	uv run pytest -m integration

test-e2e:
	uv run pytest -m e2e

frontend-install:
	cd frontend && npm install

frontend-build:
	cd frontend && npm run build

frontend-test:
	cd frontend && npm run test

frontend-lint:
	cd frontend && npm run lint

# --- Ops dashboard (ops/) ---------------------------------------------------
ops-frontend-install:
	cd ops/frontend && npm install

ops-frontend-build:
	cd ops/frontend && npm run build

# The ops backend + raj-monitor SDK keep their own lightweight test setup.
# raj-monitor is flat-layout (its types.py shadows the stdlib if the package
# dir itself lands on sys.path), so install it and run pytest from the root.
ops-backend-test:
	cd ops/backend && python -m pip install -q -r requirements.txt -r requirements-dev.txt && python -m pytest -q
	python -m pip install -q ./packages/raj_monitor
	python -m pytest -q packages/raj_monitor/tests

# Full local quality gate (matches CI).
verify: lint typecheck test frontend-build frontend-test ops-frontend-build

compose-up:
	docker compose -f deploy/compose/docker-compose.yml up --build

compose-down:
	docker compose -f deploy/compose/docker-compose.yml down

compose-logs:
	docker compose -f deploy/compose/docker-compose.yml logs -f api trading-engine market-data

migrate:
	uv run alembic -c backend/alembic.ini upgrade head

seed:
	uv run python scripts/seed.py
