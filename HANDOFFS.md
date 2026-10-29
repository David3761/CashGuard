# HANDOFFS: work done on someone else's behalf

> **Team rule (2026-10-29):** when one of us needs something another person owns, we **build it ourselves and log it here**. We don't skip it and we don't wait. Each entry says what was meant and how to reconcile it, so the AI (or person) doing the merge knows what to keep.
>
> Owners: bomboe = backend platform (B*, F3) · danutu = engine & calculations (E*) · DGAdavid1 (David G.) = foundations F1/F2, context (C*), agent (A*), data/demo/quality (D*) · David V. = Flutter app.
> Status: 🟢 in place · 🔁 replaced by the owner's version (keep the entry for history)

## Entry format

```markdown
### H-<n> · <owner> <task> · <short title> · <status>
- **Date / by:** YYYY-MM-DD, who did it (for which task of theirs)
- **Why it was needed:** what was blocked without it
- **What was done:** files + behaviour
- **Decisions taken on the owner's behalf:** values, names, defaults the owner may want to change
- **Merge instruction:** keep ours / replace with the owner's / merge like this; and what to check after the merge
```

---

## Entries

### H-1 · bomboe B1 · minimal `docker-compose.yml` with only `db-test` · 🟢
- **Date / by:** 2026-10-29, DGAdavid1 (F1.1)
- **Why it was needed:** F1 ships the `make db-up` target (work-breakdown F1); without a compose file it can't run, and everyone's `db` tests need a test Postgres.
- **What was done:** `backend/docker-compose.yml` with one service, `db-test`: `postgres:16`, host port **5433**, data on `tmpfs` (fast and throwaway), user/password/db `cashguard_test`. The healthcheck runs **`pg_isready -h 127.0.0.1` (over TCP)**. Over the Unix socket it would pass on the entrypoint's temporary init server before port 5433 accepts connections. `make db-up` = `docker compose up -d --wait db-test`; `make db-down` removes **only** `db-test`.
- **Decisions taken on the owner's behalf:** the service name `db-test`, port 5433 and tmpfs follow work-breakdown F3. The credentials `cashguard_test` / `cashguard_test` / `cashguard_test` are ours.
- **Merge instruction:** **bomboe's full B1 compose wins** (db, keycloak, api, cron). Keep a `db-test` service with port 5433, tmpfs, the same credentials and the **TCP** healthcheck, or update `TEST_DATABASE_URL` in `backend/app/config.py` and `backend/.env.example` (both added in F1.2) to match. Check afterwards: `make db-up`, then connect over TCP right away (`psql -h localhost -p 5433 -U cashguard_test`); `make db-down` must leave the other services running.

### H-2 · bomboe B1/B14 · packaging: uv + generated `requirements.txt` · 🟢
- **Date / by:** 2026-10-29, DGAdavid1 (F1.1), agreed with David G.
- **Why it was needed:** F1 needs a dependency set for everyone. bomboe had created an empty `backend/requirements.txt`, while the spec says uv + pyproject.
- **What was done:** `backend/pyproject.toml` + `backend/uv.lock` are the source of truth. `backend/requirements.txt` holds the runtime deps, **generated** by `make requirements` (`uv export`). `make check` fails if it's out of date.
- **Decisions taken on the owner's behalf:** the app is started with the factory: `uvicorn app.main:create_app --factory --workers 1` (there's no module-level `app` object, so importing has no side effects).
- **Merge instruction:** keep ours. bomboe's Dockerfile can either `pip install -r requirements.txt` or `uv sync --locked --no-dev`. The CMD must use `--factory` and **1 worker** (in-memory WebSocket manager, arch 5.2). Never edit `requirements.txt` by hand: change `pyproject.toml`, then `make requirements`.

### H-3 · bomboe (architecture doc) · doc paths `api/` → `backend/` · 🟢
- **Date / by:** 2026-10-29, DGAdavid1 (DOC-0)
- **Why it was needed:** bomboe created `backend/` as the app folder (6214a5d), but every doc, including his architecture doc, still pointed at `api/…`. Teammates and their Claude sessions read those paths.
- **What was done:** repo-folder paths rewritten to `backend/` in `README.md`, `TASKS.md`, `DGAREADME1.md`, `DGAdavid1.md`, `Bomboe.md`, `Danutu.md`, `backend/docs/{savings-coach-backend-architecture,work-breakdown,how-we-work}.md`. In the arch doc this covers §3 env file, the §5 tree root + note, §14 1b, §16.3, §16.4 and §16.5. Gap-review G-71 is annotated as reversed. **Not changed:** routes (`/api/...`), the routers package `app/api/` and `tests/api/` in the folder trees, the git branch prefix `api/<task-id>` in how-we-work §9, and the historical changelog lines in DGAREADME1 §9.
- **Decisions taken on the owner's behalf:** none beyond the paths.
- **Merge instruction:** keep ours. If bomboe edited the same docs meanwhile, take his content and re-apply the path rule above. Check afterwards: no repo-path `api/` remains outside the exceptions, and every relative `.md` link resolves (a link check, as in report DOC-0).

### H-4 · bomboe F3 · `tests/conftest.py` with the shared hypothesis profile · 🟢
- **Date / by:** 2026-10-29, DGAdavid1 (orchestrator prep, moved forward from F1.3 so the parallel agents don't each create it)
- **Why it was needed:** property tests (F2 money splits, C2 "never raises") need one deterministic hypothesis profile (how-we-work §7). The root conftest is bomboe's F3 file.
- **What was done:** `backend/tests/conftest.py` registers and loads the profile `cashguard` (`derandomize=True`, `deadline=None`, `print_blob=True`); `tests/unit/test_hypothesis_profile.py` asserts it's active.
- **Decisions taken on the owner's behalf:** `deadline=None` (parallel runs make timing deadlines flaky).
- **Merge instruction:** merge. F3 adds its fixtures (`db`, `db_committed`, `client`, `as_user`, `make_token`, `ws_connect`, `seeded_db`) to this file and keeps the profile block. Check afterwards: `test_hypothesis_profile.py` passes.
- **Extension (2026-10-29, F1.2, merged 833c644):** the conftest also has:
  - a hermetic `settings` fixture
  - an **autouse isolation fixture**: every test runs with no `.env` file and no Settings variables in the environment, and the settings cache is cleared. Tests marked `live` opt out, so they see the real key.
  - a shared `make_client(app, *, raise_app_exceptions=True)` ASGI client fixture

  F3's `client` fixture should build on `make_client` and `create_app(settings)`. Keep the isolation block, because without it a test could read a developer's real `.env` and make paid Claude calls. Check: `tests/unit/test_isolation.py` passes.

### H-5 · bomboe B1/B5/B14/F3 · env var names, local defaults, `.env.example` · 🟢
- **Date / by:** 2026-10-29, DGAdavid1 (F1.2, merged 833c644)
- **Why it was needed:** A1 and F3 need `Settings` before bomboe's B1 exists, and work-breakdown F1 ships `.env.example`.
- **What was done:** `backend/app/config.py` `Settings` (field names = env names, frozen, unknown variables ignored, `backend/.env` read by absolute path, an empty value means "unset", every value whitespace-stripped, errors never print the input value) + `backend/.env.example` + a no-drift test (parsed with python-dotenv). `create_app(settings=None)` stores the settings in `app.state.settings`; the typed dependency is `get_app_settings(request)`.
- **Decisions taken on the owner's behalf:**
  - dev DB `postgresql+psycopg://cashguard:cashguard@localhost:5432/cashguard` (a `db` service with user/password/db `cashguard`, port 5432). DB URLs **must** be `postgresql+psycopg://user:password@host:port/db` (psycopg 3; plain `postgresql://` means psycopg2, which isn't installed), checked at startup.
  - `KEYCLOAK_ISSUER` example `http://localhost:8080/realms/cashguard`; it must be `http(s)://host[:port][/prefix]/realms/<realm>`, with the trailing `/` dropped.
  - `KEYCLOAK_AUDIENCE` empty (B5 decides between `azp` and `aud`); the cron secret is named `KEYCLOAK_CRON_CLIENT_SECRET` (kept in `Settings`, masked).
  - `SIM_MODE` false in code, true in the example (and in the hosted `.env`, B14). `SIM_START_DATE` must be `YYYY-MM-DD`. `LOG_LEVEL` added.
  - `TZ` isn't read by the app, but **the cron container needs `TZ=Europe/Bucharest`** so the crontab times (arch §10) are local time.
  - In Docker, env comes from compose (`env_file:`), and **`.dockerignore` must exclude `.env`** (otherwise the key is baked into the image).
- **Merge instruction:** keep the app variable names (A1/B5 read them), or rename them in `Settings` and `.env.example` together. When B1 adds compose-only variables (`POSTGRES_*`, `KC_*`, `KEYCLOAK_ADMIN*`) to `.env.example`, add them to `NON_APP_KEYS` in `tests/unit/test_config.py`; the drift test names the missing ones. Check: `uv run pytest tests/unit/test_config.py`, then `docker compose config` resolves every `${VAR}`.

### H-6 · bomboe B2/B5/B7/B10/B12 · conventions in clock (+ errors, logging when F1.4/F1.5 land) · 🟢
- **Date / by:** 2026-10-29, DGAdavid1 (F1.3, merged 17dde21)
- **Why it was needed:** every one of bomboe's tasks reads the time, and B10's simulator must replace the clock.
- **What was done:** `backend/app/clock.py`:
  - `APP_TZ = Europe/Bucharest`, fixed; the OS `TZ` is ignored.
  - a `Clock` protocol (`now()`, `today()`), `RealClock`, and `FixedClock(at)` (aware datetimes only, normalised through UTC)
  - `get_clock()`, `set_clock(c) -> previous`, and the context manager `use_clock(c)` (per-block restore, so overlapping blocks are safe)
  - module-level `now()` / `today()`
  - `set_clock` / `use_clock` **validate** the clock once at install: no classes; `now()` must be aware with Bucharest's offset; `today()` must return a `date` equal to `now().date()`

  The ban on direct wall-clock calls (`datetime.now/utcnow/today`, `date.today`, `time.time/time_ns/localtime/gmtime/strftime/ctime/asctime/clock_gettime*`) is enforced by ruff TID251 and an AST test. The test also catches aliases, `default_factory=datetime.now` and SQLAlchemy `default=datetime.now`.
- **Decisions taken on the owner's behalf:**
  - B10's SimClock is installed with `set_clock`/`use_clock` and must pass `test_every_clock_keeps_the_contract` (add it to that test's clock list). If it builds `now()` from the sim date plus a time of day, it takes the time from `RealClock().now()`, never `datetime.now()` (`app/sim/` isn't exempt from the ban).
  - B2 models use `default_factory=clock.now` (never `datetime.now`).
  - Tests use `with clock.use_clock(FixedClock(...))`; every test starts and ends with a fresh `RealClock` (conftest).
  - **Team rule (PEP 495):** a Bucharest datetime in the repeated or skipped DST hour is never `==` to the same instant in another zone, so compare instants via `.astimezone(UTC)`.
- **Merge instruction:** keep ours. B10 adds `app/sim/clock_store.py`'s SimClock and registers it in the contract test. Check: `make check` (the architecture test + the contract test) passes with SimClock installed.

