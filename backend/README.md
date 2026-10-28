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
make db-up        # Postgres for tests (port 5435)
make check        # ruff + mypy + tests (everything except live)
make up           # the whole stack: db, keycloak, api (migrates on start), cron
```

| Service | URL / port | Login |
|---|---|---|
| API | http://localhost:8000/api/health | Bearer token from Keycloak |
| Keycloak | http://localhost:8081 (admin console `/admin`) | `admin` / `admin` |
| Dev DB (`cashguard` app tables, `keycloak` Keycloak's tables) | `localhost:5434` | `cashguard` / `cashguard` |
| Test DB (throwaway, tmpfs) | `localhost:5435` | `cashguard` / `cashguard` |

Persona users (`matei`, `andrei`, `bianca`, `ioana`, `alex`) have the password `KC_DEMO_PASSWORD` (dev default `cashguard-dev`). A token for scripts:
`curl -d grant_type=password -d client_id=savings-dev -d username=matei -d password=cashguard-dev http://localhost:8081/realms/cashguard/protocol/openid-connect/token`

## Database migrations (Alembic)

The schema lives in `app/db/models.py`; `migrations/versions/` holds the migrations that build it. The API container runs `alembic upgrade head` on start; tests build the test DB with the same migrations.

```bash
uv run alembic upgrade head                                 # migrate the dev DB (DATABASE_URL)
uv run alembic revision --autogenerate -m "add pots.color"  # after changing models.py
uv run python -m app.db.init --reset                        # drop every table + migrate (deletes data)
```

After `--autogenerate`, **read the generated file** before committing. Autogenerate misses:
- **CHECK changes**, e.g. a new enum value. Add `replace_enum_check("table", "column", TheEnum)` from `app.db.migration_helpers` for every column using that enum (`tests/db/test_schema_life.py::ENUM_COLUMNS` lists them).
- **FKs that close a cycle** (`use_alter=True`). Add them with `op.create_foreign_key` after both tables exist (see the initial migration).

Safety nets in `tests/db/test_migrations.py`: the migrated schema must equal the models (a forgotten migration fails), there must be **one head** (two people adding migrations in parallel → `uv run alembic merge heads`), and upgrade/downgrade must round-trip.

## Commands

| Command | What |
|---|---|
| `make test` | unit + db + api + ws tests |
| `make check` | lint + types + tests |
| `make fmt` | format + autofix |
| `make db-up` / `make db-down` | test Postgres |
| `make up` / `make down` | the whole stack |
| `uv run pytest tests/unit/test_clock.py -q` | one file |
| `uv run pytest -m live tests/eval` | real Claude, on purpose only |
