# CashGuard API (backend)

FastAPI + PostgreSQL + Keycloak. Architecture: [`docs/savings-coach-backend-architecture.md`](docs/savings-coach-backend-architecture.md).
How we work: [`docs/how-we-work.md`](docs/how-we-work.md).

> The docs say `api/`; the folder is `backend/`. Everything else (the `app/` package, the paths inside it) is as documented.

## Run locally

```bash
# once: install uv (https://docs.astral.sh/uv/), e.g. `pipx install uv`
cd backend
cp .env.example .env
uv sync
make db-up        # Postgres for tests (port 5433)
make check        # ruff + mypy + tests (everything except live)
make dev          # API on http://localhost:8000/api/health
```

## Commands

| Command | What |
|---|---|
| `make test` | unit + db + api + ws tests |
| `make check` | lint + types + tests |
| `make fmt` | format + autofix |
| `make db-up` / `make db-down` | test Postgres |
| `uv run pytest tests/unit/test_clock.py -q` | one file |
| `uv run pytest -m live tests/eval` | real Claude, on purpose only |
