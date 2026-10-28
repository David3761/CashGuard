# CashGuard backend

One FastAPI app with every backend module: platform (bomboe), `engine/` (danutu), `context/` + `agent/` (David G.).

- **What we build:** [`docs/savings-coach-backend-architecture.md`](docs/savings-coach-backend-architecture.md) (source of truth)
- **How (tasks, conventions, tests):** [`docs/work-breakdown.md`](docs/work-breakdown.md), with the folder layout in §0.2
- **How we work (step loop, reports, reviews):** [`docs/how-we-work.md`](docs/how-we-work.md)
- **Work done on someone else's behalf:** [`../HANDOFFS.md`](../HANDOFFS.md)

## Setup

Needs Python 3.12 and [uv](https://docs.astral.sh/uv/). Docker is needed only for the database tests.

```bash
cd backend
make install        # uv sync: creates .venv with the app + dev dependencies
cp .env.example .env   # local settings; add ANTHROPIC_API_KEY only for real Claude calls
make dev            # http://localhost:8000/api/health → {"status":"ok"}
```

The app has no module-level instance; it's always started through the factory:
`uv run uvicorn app.main:create_app --factory --workers 1` (1 worker: the WebSocket manager is in memory, arch 5.2).

## Settings

All configuration is environment variables, read by `Settings` in `app/config.py` (field names = variable names, e.g. `settings.ANTHROPIC_MODEL`). [`.env.example`](.env.example) lists every one; a test fails if the two drift apart.

- Sources: real environment variables, then `backend/.env`, then the code defaults. An empty value means "not set"; surrounding spaces never matter.
- Secrets (`*_DATABASE_URL`, `ANTHROPIC_API_KEY`, `KEYCLOAK_CRON_CLIENT_SECRET`) are `SecretStr`: they never show in `repr` or dumps; read them with `.get_secret_value()`.
- An invalid value stops the app at startup with an error naming the variable (the value itself isn't printed, so a rejected `DATABASE_URL` doesn't show its password). DB URLs must be `postgresql+psycopg://user:password@host:port/db`; `KEYCLOAK_ISSUER` must be a realm URL (`…/realms/<name>`); `SIM_START_DATE` is `YYYY-MM-DD`.
- `TZ` is not read by the app: day boundaries are always Europe/Bucharest (`app/clock.py`).
- In code: `create_app(settings)` stores them; routes use `Depends(get_app_settings)`; classes take a `Settings` argument. Only `create_app()` and command-line entry points call `get_settings()`.
- In tests: every test is isolated automatically (`tests/conftest.py`): `Settings()` and `get_settings()` see only the code defaults plus what the test sets (`monkeypatch.setenv`), never your real `.env` or shell variables; and no `ANTHROPIC_*` variable reaches the anthropic SDK (it reads `ANTHROPIC_BASE_URL`, `ANTHROPIC_LOG`, … by itself). Tests marked `live` opt out, so they can use the real key on purpose. The `settings` fixture gives the defaults; `make_client(app)` gives an in-process HTTP client.

## Everyday commands

| Command | What it does |
|---|---|
| `make check` | lock check + `ruff` + `mypy` + every non-live test. **Must be green before a review.** |
| `make test` | Every test except `live`, with coverage |
| `make fmt` | Format and auto-fix lint |
| `make db-up` / `make db-down` | Start/stop the test Postgres (port 5433, data in tmpfs) |
| `make test-all` | Also runs `live` tests: **real Claude, costs money** |
| `uv run pytest tests/api/test_health.py -q` | One file |

## Dependencies

`pyproject.toml` + `uv.lock` are the source of truth. Add a package with `uv add <pkg>` (or `uv add --dev <pkg>`); after a hand edit of `pyproject.toml` run `uv lock`. Then run `make requirements`. `requirements.txt` (runtime only, for the Docker image) is **generated**; never edit it by hand. `make check` fails if it's out of date.

## Test markers

`db` (needs `make db-up`) · `api` · `ws` · `live` (real Anthropic API, excluded by default) · `slow`. Unmarked tests are pure unit tests.
