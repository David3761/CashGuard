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
make dev            # http://localhost:8000/api/health → {"status":"ok"}
```

The app has no module-level instance; it's always started through the factory:
`uv run uvicorn app.main:create_app --factory --workers 1` (1 worker: the WebSocket manager is in memory, arch 5.2).

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
