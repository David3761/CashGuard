UV ?= uv

.PHONY: dev test test-all check lint typecheck fmt db-up db-down up down

dev:
	$(UV) run uvicorn app.main:app --reload --port 8000

test:                 ## unit + db + api + ws (everything except live)
	$(UV) run pytest -q

test-all:             ## also the live LLM tests (costs money)
	$(UV) run pytest -q -m ""

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

typecheck:
	$(UV) run mypy app

check: lint typecheck test

fmt:
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

db-up:                ## Postgres for tests
	docker compose up -d --wait db-test

db-down:
	docker compose stop db-test

up:
	docker compose up -d --build

down:
	docker compose down
