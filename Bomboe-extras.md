# Bomboe: work done outside my assignment

> Everything here was built on branch `bomboe` because it blocked my tasks and didn't exist yet on any branch.
> **Owner of each item: read the row, keep or replace my version, and tell me if a name or signature changes** so my code (B1–B15) follows.
> Rule I followed: implement the owner's spec exactly (DGAdavid1.md / work-breakdown), nothing extra unless listed under "Additions".

## Repo-level changes

| Change | Why | Merge note |
|---|---|---|
| `api/` → `backend/` (docs moved to `backend/docs/`) | done by bomboe before this work | Every doc still says `api/`; paths inside (`app/`, `tests/`, `data/`) are unchanged |
| Root `.gitignore` (Python, `.env*` except `.env.example`, editors, OS files) | F1 asked for `.gitignore` additions | `mobile/.gitignore` untouched |
| Removed the empty `backend/requirements.txt` and `backend/.gitkeep` | we use uv + `pyproject.toml` (work-breakdown 0.1) | — |

## F1 (owner: David G.) — minimal skeleton, done 2026-10-29

| File | What's in it | Differences from the F1 spec |
|---|---|---|
| `backend/pyproject.toml`, `uv.lock`, `.python-version` | deps from work-breakdown 0.1 (main + dev group); ruff; mypy (strict-ish flags for `app.domain/engine/context`, `disallow_untyped_defs` for all of `app`); pytest markers `db api ws live slow`, default `-m 'not live'`, asyncio auto, **session-scoped event loop** | `[tool.uv] package = false` (the app isn't installed as a package; `pythonpath = ["."]` for pytest) |
| `backend/Makefile` | `dev test test-all lint typecheck check fmt db-up db-down up down` | extra targets `lint`, `typecheck`, `up`, `down` |
| `backend/.env.example` | every var of arch §3 | dev DB on host port **5434** (5432 is often taken by a local Postgres) |
| `app/config.py` | `Settings` (pydantic-settings) + `get_settings()` (cached) | adds `TEST_DATABASE_URL`, `LOG_LEVEL`; no cron secret (only the cron container needs it, B1) |
| `app/clock.py` | `Clock` protocol, `RealClock`, `FixedClock` (+ `FixedClock.on(date)`), `get_clock`/`set_clock`, module `today()`/`now()` | adds helpers `to_local(dt)` and `local_date(dt)` (Bucharest day of an instant; used by B3 `question_asked_today` and the ledger) |
| `app/errors.py` | `DomainError(code, message, status=400)`; handlers for `DomainError`, `RequestValidationError` (422 `invalid_request`), `HTTPException` (404 → `not_found`, …) and `Exception` (500 `internal_error`, no stack trace) | the HTTPException handler is extra (needed for the 404 envelope) |
| `app/logging.py` | `configure_logging(level)`: JSON lines on stdout | — |
| `app/main.py` | `create_app(settings=None)`, router at `/api`, `GET /api/health`, OpenAPI at `/api/openapi.json` | — |
| `tests/unit/test_config.py`, `test_clock.py`, `test_app.py` | the F1 test list (Settings env/.env, SIM_MODE spellings, optional key None, secret not logged; clock + DST 2026-10-25; health, 404, DomainError, 422, 500 envelopes) | — |

**Later changes to F1 files from my tasks (keep them when merging):**

| File | Change | From |
|---|---|---|
| `pyproject.toml` | dev dependency `shellcheck-py` (the B1 cron test runs shellcheck); ruff `extend-exclude = ["*.md"]` (ruff 0.17 reformats code blocks in the shared docs otherwise) | B1 |
| `app/config.py` | `KEYCLOAK_INTERNAL_URL: str \| None` (where the API fetches discovery/JWKS inside docker; defaults to the issuer); default issuer port **8081**; test DB port **5435** | B1 |

## F2 step 1 (owner: David G.) — enums only

| File | What's in it | Notes |
|---|---|---|
| `app/domain/enums.py` | every `StrEnum` of the F2 list, values copied from arch 4.4/4.5 | **Not done:** `money.py`, `models.py`, `results.py`, `tests/builders.py` |
| `tests/unit/test_enums.py` | golden value list per enum | — |

**Additions** (not in the F2 list, needed for the DB CHECK constraints in B2; values from arch 4.1/4.2):
`TransactionStatus` (unresolved/processing/resolved/failed), `TransactionSource` (seed/sim), `GoalStatus` (active/completed), `LifeEventType` (trip/gift/social/purchase/education/other, from the `add_life_event` tool schema in 6.2), `LifeEventStatus` (planned/done/cancelled), `LedgerStatus` (ok/warning/overspent/under), `MessageRole` (user/assistant), `AgentTrigger` (chat/proactive), `AgentRunStatus` (running/completed/failed — 🟡 my pick, the arch doc doesn't list them), `ToolCallStatus` (ok/error).
