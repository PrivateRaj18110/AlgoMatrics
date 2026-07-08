.PHONY: install dev-secrets lint format typecheck test test-integration test-e2e \
        frontend-install frontend-build frontend-test frontend-lint \
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

# Full local quality gate (matches CI).
verify: lint typecheck test frontend-build frontend-test

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
