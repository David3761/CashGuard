# Run every target from backend/. `make help` lists them.
.DEFAULT_GOAL := help
# --locked: fail (instead of exporting a stale lock) when pyproject.toml changed without `uv lock`.
UV_EXPORT := uv export --format requirements-txt --no-dev --no-hashes --locked

.PHONY: help install dev fmt lint typecheck test test-all requirements lock-check check db-up db-down keycloak-sync

help:  ## List the targets
	@grep -E "^[a-z-]+:.*## " $(MAKEFILE_LIST) | sed "s/:.*## /\t/"

install:  ## Install the app and dev dependencies (.venv) exactly as locked
	uv sync --locked

dev:  ## Run the API locally with reload on http://localhost:8000
	uv run uvicorn app.main:create_app --factory --reload --port 8000

fmt:  ## Format and auto-fix lint issues
	uv run ruff format .
	uv run ruff check --fix .

lint:  ## Check formatting and lint (no changes)
	uv run ruff format --check .
	uv run ruff check .

typecheck:  ## mypy (strict on the cores, see pyproject)
	uv run mypy app tests

test:  ## Every test except live (unit, db, api, ws), with coverage
	uv run pytest --cov

test-all:  ## Every test INCLUDING live ones (real Claude: costs money), with coverage
	uv run pytest --cov -m ""

requirements:  ## Regenerate requirements.txt from uv.lock (never edit it by hand)
	@set -e; tmp=$$(mktemp); trap 'rm -f "$$tmp"' EXIT; \
	$(UV_EXPORT) > "$$tmp"; cat "$$tmp" > requirements.txt

lock-check:  ## uv.lock matches pyproject and requirements.txt matches uv.lock
	uv lock --check
	@set -e; tmp=$$(mktemp); trap 'rm -f "$$tmp"' EXIT; \
	$(UV_EXPORT) > "$$tmp"; \
	diff -q "$$tmp" requirements.txt > /dev/null \
		|| { echo "requirements.txt is out of date: run make requirements"; exit 1; }

check: lock-check lint typecheck test  ## Everything that must be green before a review

db-up:  ## Start the test Postgres (port 5435, tmpfs)
	docker compose up -d --wait db-test

db-down:  ## Stop and remove only the test Postgres (other compose services keep running)
	docker compose rm --stop --force db-test

keycloak-sync:  ## Add the realm file's new users/roles/settings to a running Keycloak (KC_URL, KC_ADMIN_*)
	uv run python scripts/keycloak_sync.py
