# CashGuard backend

One FastAPI app with every backend module: platform (bomboe), `engine/` (danutu), `context/` + `agent/` (David G.).

- **What we build:** [`docs/savings-coach-backend-architecture.md`](docs/savings-coach-backend-architecture.md) (source of truth)
- **How (tasks, conventions, tests):** [`docs/work-breakdown.md`](docs/work-breakdown.md), with the folder layout in §0.2
- **How we work (step loop, reports, reviews):** [`docs/how-we-work.md`](docs/how-we-work.md)
- **Work done on someone else's behalf:** [`../HANDOFFS.md`](../docs/team/HANDOFFS.md)

## Setup

Needs Python 3.12 and [uv](https://docs.astral.sh/uv/). Docker is needed only for the database tests.

```bash
cd backend
make install        # uv sync: creates .venv with the app + dev dependencies
cp .env.example .env   # local settings; add the Claude credentials (below) only for real Claude calls
make dev            # http://localhost:8000/api/health → {"status":"ok"}
```

**Claude credentials** (optional: without them the agent answers with templates and the deterministic fallbacks). Set one provider in `backend/.env`:

- **Amazon Bedrock** (the hackathon's): `LLM_PROVIDER=bedrock`, `AWS_DEFAULT_REGION=us-west-2`, and a Bedrock API key in `AWS_BEARER_TOKEN_BEDROCK` (preferred) or the temporary `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN`. The model `claude-sonnet-5-5` becomes the cross-region inference profile `us.anthropic.claude-sonnet-5-5`, and `ANTHROPIC_REFUSAL_FALLBACK` is ignored.
- **Claude API:** `LLM_PROVIDER=anthropic` (the default) and `ANTHROPIC_API_KEY`.

The app has no module-level instance; it's always started through the factory:
`uv run uvicorn app.main:create_app --factory --workers 1` (1 worker: the WebSocket manager is in memory, arch 5.2).

## Settings

All configuration is environment variables, read by `Settings` in `app/config.py` (field names = variable names, e.g. `settings.ANTHROPIC_MODEL`). [`.env.example`](.env.example) lists every one; a test fails if the two drift apart.

- Sources: real environment variables, then `backend/.env`, then the code defaults. An empty value means "not set"; surrounding spaces never matter.
- Secrets (`*_DATABASE_URL`, `ANTHROPIC_API_KEY`, `AWS_BEARER_TOKEN_BEDROCK`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `KEYCLOAK_CRON_CLIENT_SECRET`) are `SecretStr`: they never show in `repr` or dumps; read them with `.get_secret_value()`.
- An invalid value stops the app at startup with an error naming the variable (the value itself isn't printed, so a rejected `DATABASE_URL` doesn't show its password). DB URLs must be `postgresql+psycopg://user:password@host:port/db`; `KEYCLOAK_ISSUER` must be a realm URL (`…/realms/<name>`); `SIM_START_DATE` is `YYYY-MM-DD`.
- `TZ` is not read by the app: day boundaries are always Europe/Bucharest (`app/clock.py`).
- In code: `create_app(settings)` stores them; routes use `Depends(get_app_settings)`; classes take a `Settings` argument. Only `create_app()` and command-line entry points call `get_settings()`.
- In tests: every test is isolated automatically (`tests/conftest.py`): `Settings()` and `get_settings()` see only the code defaults plus what the test sets (`monkeypatch.setenv`), never your real `.env` or shell variables; and no `ANTHROPIC_*` variable reaches the anthropic SDK (it reads `ANTHROPIC_BASE_URL`, `ANTHROPIC_LOG`, … by itself). Tests marked `live` opt out, so they can use the real key on purpose. The `settings` fixture gives the defaults; `make_client(app)` gives an in-process HTTP client.

## Time

Time comes only from `app/clock.py`. ruff bans `datetime.now()`, `time.time()`, `time.localtime()` and the other wall-clock reads everywhere else, and an architecture test double-checks `app/`, including aliases and references like `default_factory=datetime.now`.

- In the shell (services, pipeline, endpoints): `clock.now()` (timezone-aware, Europe/Bucharest) and `clock.today()` (the Bucharest date). Pure cores (`engine/`, `context/`) receive `today` as a parameter.
- Day boundaries are Bucharest's whatever the server's `TZ`: midnight is 21:00Z in summer and 22:00Z in winter.
- To compare instants from different zones, compare `.astimezone(UTC)` values. During the repeated DST hour, Python never treats a Bucharest datetime as `==` to the same instant in UTC (PEP 495).
- In tests: `with clock.use_clock(FixedClock(datetime.fromisoformat("2026-06-15T09:00:00Z"))):` (write instants in UTC). Blocks may overlap and end in any order; each removes only its own clock. Every test starts and ends with a fresh real clock (conftest).
- The simulator (B10) installs its `SimClock` for the whole process with `clock.set_clock(...)`. Both `set_clock` and `use_clock` check that the clock really works: an instance, an aware Bucharest `now()`, a `date` `today()` equal to `now()`'s date.

## Errors

Every non-2xx response is `{"error": {"code": "...", "message": "..."}}` (arch 9.1), built by `app/errors.py`, which `create_app()` installs.

- Raise `DomainError("agent_busy", "The assistant is still answering your previous message.", status=409, headers={"Retry-After": "5"})` anywhere: in a route, a dependency or a middleware. The code is snake_case (≤ 64 chars) and stable: the app branches on it. The status is 400–599 (default 400). `headers` are optional, e.g. `WWW-Authenticate` on a 401; they must be single-line and can't set Content-Length/Content-Type. The message is English text for developers/Claude; the app shows its own UI text per code.
- On a WebSocket a `DomainError` closes the socket: code 1008 (1011 for 5xx), reason = the code, never the message.
- F1's codes: `validation_error` (422: `field.path: fixed text` for up to 5 fields; nothing the client sent, no dict keys or unknown names, no internal validator names), `not_found` (404), `method_not_allowed` (405, with an `Allow` listing every method of the path), `internal_error` (500, generic message; the traceback goes only to the server log), `http_<status>` for other framework errors (a text detail is kept, a structured one isn't).
- Don't raise `HTTPException` with a dict detail; raise a `DomainError`. OpenAPI documents the envelope as every route's `default` response.

## Everyday commands

| Command | What it does |
|---|---|
| `make check` | lock check + `ruff` + `mypy` + every non-live test. **Must be green before a review.** |
| `make test` | Every test except `live`, with coverage |
| `make fmt` | Format and auto-fix lint |
| `make db-up` / `make db-down` | Start/stop the test Postgres (port 5435, data in tmpfs) |
| `make test-all` | Also runs `live` tests: **real Claude, costs money** |
| `uv run pytest tests/api/test_health.py -q` | One file |

## Dependencies

`pyproject.toml` + `uv.lock` are the source of truth. Add a package with `uv add <pkg>` (or `uv add --dev <pkg>`); after a hand edit of `pyproject.toml` run `uv lock`. Then run `make requirements`. `requirements.txt` (runtime only, for the Docker image) is **generated**; never edit it by hand. `make check` fails if it's out of date.

## Test markers

`db` (needs `make db-up`) · `api` · `ws` · `live` (real Anthropic API, excluded by default) · `slow`. Unmarked tests are pure unit tests.
