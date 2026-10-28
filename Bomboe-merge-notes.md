# Bomboe: merge notes (branch `bomboe`)

> **What this is:** everything built on branch `bomboe`: my tasks (Bomboe.md), the pieces of other people's tasks I had to build because they blocked mine, every decision that changes a team convention, and every deviation from the spec. Updated after every step.
> **Before merging** another branch with this one, read §0 and §1. **If you own something in §2**, keep or replace my version and tell bomboe if a name or signature changes.

---

## 0. Merge checklist

1. `cd backend && uv sync && make db-up && make check` is green on `bomboe` (last run: see §5).
2. Files most likely to conflict, and what to keep:
   | File | Rule |
   |---|---|
   | `backend/pyproject.toml` | union of dependencies; keep `alembic`, `shellcheck-py`, the ruff excludes / per-file-ignores and the pytest settings below |
   | `backend/app/config.py` | union of settings; keep `KEYCLOAK_INTERNAL_URL`, `TEST_DATABASE_URL`, ports 8081 / 5434 / 5435 |
   | `backend/app/domain/enums.py` | union; values must stay exactly the strings in arch 4.4/4.5 (they're in DB CHECKs). **Any value change needs a migration** (§1, Alembic) |
   | `backend/app/main.py`, `errors.py`, `clock.py` | keep the function names listed in §2; merge bodies |
   | `backend/tests/conftest.py` | keep `pytest_plugins`, the folder→marker hook and the autouse `fixed_clock` |
3. If your branch changed `app/db/models.py`: rebase on `bomboe`, then `uv run alembic revision --autogenerate -m "…"` on top of the current head and read the file (backend/README.md, "Database migrations").
4. After merging: `make check` again (the single-head test catches parallel migrations).

---

## 1. Changes that affect everyone

| What | The docs say | Now | Why | What you do |
|---|---|---|---|---|
| Folder | `api/` | **`backend/`** (docs in `backend/docs/`) | renamed by bomboe | read every `api/…` path in the docs as `backend/…` |
| Schema management | `metadata.create_all`, "no Alembic" (work-breakdown 0.1) | **Alembic migrations** in `backend/migrations/` | bomboe's decision, 2026-10-29 | change `models.py` → add a migration (`uv run alembic revision --autogenerate`), read it, commit both. Enum value added → `replace_enum_check(...)` in the migration (autogenerate can't see CHECKs) |
| Test DB | — | built with `alembic upgrade head` once per test session | tests run on the real migrated schema | nothing; `make db-up` first |
| Host ports | 8080 (Keycloak), 5433 (test DB) | API **8000**, Keycloak **8081**, dev DB **5434**, test DB **5435** | 5432/5433/8080 were taken on bomboe's machine (local Postgres, another project, pgadmin) | use these in scripts and the app's dev config |
| Test clock | — | **every test runs at 2026-06-15 12:00 Bucharest** (autouse `fixed_clock` in `tests/conftest.py`) | DB timestamps come from `app.clock.now()`; tests must be deterministic | a test that needs another time calls `clock.set_clock(FixedClock(...))` (restored automatically) |
| Test markers | per-file | **automatic by folder**: `tests/db` → `db`, `tests/api` → `api`, `tests/ws` → `ws` | less boilerplate | put files in the right folder |
| Merchant & product ids | not specified | **text slugs** (`"mega_image"`, `"pusculita_flexibila"`) | `context.normalize` is pure and reads `data/merchants.json`, so `transactions.merchant_id` must be the file's id | David G.: give each entry of `merchants.json` / `products.json` an `"id"` slug |

---

## 2. Built outside my assignment

### Repo-level

| Change | Why | Merge note |
|---|---|---|
| `api/` → `backend/` | done by bomboe before this work | see §1 |
| Root `.gitignore` (Python, `.env*` except `.env.example`, editors, OS files) | F1 asked for `.gitignore` additions | `mobile/.gitignore` untouched |
| Removed the empty `backend/requirements.txt` and `backend/.gitkeep` | uv + `pyproject.toml` (work-breakdown 0.1) | — |

### F1 (owner: David G.): minimal skeleton

| File | What's in it | Differences from the F1 spec |
|---|---|---|
| `pyproject.toml`, `uv.lock`, `.python-version` | deps from work-breakdown 0.1; ruff; mypy (strict-ish for `app.domain/engine/context`, `disallow_untyped_defs` for all of `app`); pytest markers `db api ws live slow`, default `-m 'not live'`, asyncio auto, **session-scoped event loop** | `[tool.uv] package = false` (`pythonpath = ["."]` for pytest) |
| `Makefile` | `dev test test-all lint typecheck check fmt db-up db-down up down` | extra targets `lint`, `typecheck`, `up`, `down` |
| `.env.example` | every var of arch §3 + Keycloak/cron vars (B1) | ports per §1 |
| `app/config.py` | `Settings` + `get_settings()` (cached) | adds `TEST_DATABASE_URL`, `LOG_LEVEL`, `KEYCLOAK_INTERNAL_URL` |
| `app/clock.py` | `Clock`, `RealClock`, `FixedClock` (+ `FixedClock.on(date)`), `get_clock`/`set_clock`, `today()`/`now()` | adds `to_local(dt)`, `local_date(dt)` (Bucharest day of an instant) |
| `app/errors.py` | `DomainError(code, message, status=400)`; handlers → arch 9.1 envelope: `DomainError`, 422 `invalid_request`, `HTTPException` (404 `not_found`…), 500 `internal_error` (no stack trace) | `error_response(status, code, message)` helper + the HTTPException handler are extra |
| `app/logging.py` | `configure_logging(level)`: JSON lines | — |
| `app/main.py` | `create_app(settings=None)`, `/api` router, `GET /api/health`, OpenAPI at `/api/openapi.json` | — |
| `tests/unit/test_config.py`, `test_clock.py`, `test_app.py` | the F1 test list | written after the code (not tests-first) |

Later F1-file changes from my tasks: `pyproject.toml` (+ `shellcheck-py`, `alembic`; ruff `extend-exclude = ["*.md"]` because ruff 0.17 reformats code blocks in the shared docs; E501 ignored in generated migrations), `app/config.py` (`KEYCLOAK_INTERNAL_URL`, ports).

### F2 (owner: David G.): all of it, built per DGAdavid1.md F2 steps 1–3

bomboe asked for it on 2026-10-29 because B3/B4 and the stubs return these types and nothing was on any branch.

| File | What's in it | Differences from the spec |
|---|---|---|
| `app/domain/enums.py` | every `StrEnum` of the F2 list, values from arch 4.4/4.5 | **additions** for the DB CHECKs (arch 4.1/4.2): `TransactionStatus`, `TransactionSource`, `GoalStatus`, `LifeEventType` (from the `add_life_event` schema, 6.2), `LifeEventStatus`, `LedgerStatus`, `MessageRole`, `AgentTrigger` (chat/proactive), `AgentRunStatus` (running/completed/failed, 🟡 my pick), `ToolCallStatus` (ok/error) |
| `app/domain/money.py` | `to_money` (half-up, floats via `str`), `split_share(total, people) -> (own, others)` (always adds up), `share_each(others, n)` | — |
| `app/domain/base.py` | `Frozen` base, `Money` (Decimal, rounded to 2 dp on input, **JSON number** in JSON mode), `PositiveMoney`, `NonNegativeMoney`, `Score` (float 0–1), `Weekday` (ISO 1–7), `Month` | **extra file**: `models.py` needs `PlanSummary`/`Forecast` for `UserContext` and `results.py` needs `Money`, so the shared pieces live here to avoid an import cycle |
| `app/domain/models.py` | `Item`, `TxView` (`effective_amount` defaults to `amount`), `LifeFact` (+ `active_on(day)`), typed values `OccupationValue`, `HouseholdMemberValue`, `PetValue`, `VehicleValue`, `ActivityValue`, `PriorityValue`, `LifeEventValue`, `CustomValue` (any other type), `TimeWindow`, `Signature`, `RuleMatch`, `RuleOutcome`, `PatternRule`, `Account`, `Goal`, `IncomeSource`, `FixedCost`, `LifeEvent`, `Pot`, `Receivable`, `PlanPreferences`, `Baseline`, `Merchant`, `UserProfile`, `AgentEventView`, `UserContext` | **additions**: `Account`, `Transfer` (`auto_save` returns it, arch 15.1), `LifeFactDraft` (`infer_hypotheses`, 15.1), `TimeWindow`. `PriorityValue.category` is a `Category` + a free `label` (arch's example `"concerts"` is not a category → `{"category": "entertainment", "label": "concerte"}`). `LifeEventValue` dates are `starts_on` (a field named `date` breaks Pydantic). `TimeWindow`/`RuleMatch` use `from_` in Python, `"from"` in JSON |
| `app/domain/results.py` | `QuestionHint`, `Evaluation`, `FitResult`, `QuestionCandidate`, `RuleChange`, `PropagationResult`, `AnomalyFeatures`, `DayBudget`, `PlanResult`, `PlanSummary`, `Driver`, `Option`, `Forecast`, `SimDiff`, `Solve`, `SimResult`, `AgentResult` | `Evaluation` also carries `merchant`, `annotation_source` (default `auto`), `annotation_confidence` (the pipeline saves them) |
| `tests/builders.py` | `tx()`, `history()` (resolved), `fact()`, `signature()`, `rule()` (Matei's Friday rule), `ctx()`, `matei_ctx()`, `andrei_ctx()`, `bianca_ctx()`, `ioana_ctx()`, `at(day, hh, mm)` | personas are small and hand-made from arch 16.1; numbers are not calibrated (E13 tunes the seeded data, not these) |
| tests | `tests/unit/test_enums.py`, `test_money.py` (+ hypothesis property), `test_domain_models.py` (one pass + one fail per validation rule, frozen, JSON round-trip with diacritics + emoji, money as JSON number), `test_builders.py` | — |

### F3 (mine): test fixtures ✅ (`seeded_db` after B12)

How to use them: **`backend/tests/README.md`** (one example per fixture, how to run each marker).

| Fixture | File | What |
|---|---|---|
| `engine` | `tests/fixtures/db.py` | the test DB, rebuilt with `alembic upgrade head` once per session |
| `db` | same | rolled back after the test (SAVEPOINT inside: even `commit()` stays in the test) |
| `db_committed` | same | real commits; the app's own `unit_of_work()` / `get_db()` use the test DB; every table truncated after |
| `test_keys`, `make_token`, `test_jwks` | `tests/fixtures/auth.py` | one RSA key per session; `make_token(sub, roles, exp_in, iss, azp, aud, nbf_in, kid)`; the app verifies tokens against the test key; `unsigned_token` / `hs256_with_public_key` for security tests |
| `app`, `client`, `as_user` | `tests/fixtures/api.py` | a fresh app whose `get_db` yields the test's `db` session; httpx client on `http://test/api`; `as_user(user_or_sub, roles=(), **token_kw)` |
| `ws_client`, `ws_connect` | `tests/fixtures/ws.py` | Starlette TestClient; `ws_connect(user, path="/ws", token=None)` → `/ws?token=…` (other thread + loop: use committed data) |
| `fixed_clock` (autouse) | `tests/conftest.py` | app clock at 2026-06-15 12:00 Bucharest |

Spec note: F3.2 says a token with `exp_in=-1` must fail with `token_expired`, but B5.1 asks for a 30 s leeway, so `-1` is still valid. I followed B5 (tests use `exp_in=-31`).

---

## 3. My tasks: what exists and how to use it

### B1 · docker-compose, Keycloak, cron ✅ steps 1–3 (step 4 smoke waits for `/me` + `/internal/process`)

| Piece | Where | Notes for others |
|---|---|---|
| Stack | `backend/docker-compose.yml` | `db` (Postgres 16; databases `cashguard` = app, `keycloak` = Keycloak), `db-test` (tmpfs), `keycloak` 26.5.0, `api` (migrates, then 1 uvicorn worker), `cron` |
| Keycloak storage | `keycloak` DB in `db`; created by `backend/db/init/01-keycloak.sh` on the volume's first start | users, clients, roles persist across restarts |
| Realm seed | `backend/keycloak/realm-cashguard.json` (imported on first start only) | clients `savings-frontend` (public, PKCE S256, redirects `ro.cashguard.app:/oauthredirect`, `http://localhost:*`), `savings-cron` (service account, role `internal`), `savings-dev` (password grant, **dev only**); access token 1800 s |
| Persona users | `matei` `andrei` `bianca` `ioana` `alex`, ids `a0000000-0000-4000-8000-00000000000{1..5}` | **these ids are `users.keycloak_sub` in the seed (B12)**; password `KC_DEMO_PASSWORD` (dev `cashguard-dev`) |
| Issuer | `KC_HOSTNAME` (dev `http://localhost:8081`) = API's `KEYCLOAK_ISSUER` | inside docker the API fetches keys from `KEYCLOAK_INTERNAL_URL=http://keycloak:8080/realms/cashguard` |
| Cron | `backend/cron/{Dockerfile,crontab,run.sh}` | crontab = arch §10; `run.sh [--dry-run] <endpoint>` gets a client-credentials token, POSTs `/api/internal/<endpoint>`; `CRON_ENABLED_JOBS` (default `all`; demo idea: `"process recover"`, Q21) |

### B2 · Database schema ✅ (waiting for review)

| Piece | Where | Notes for others |
|---|---|---|
| Models | `backend/app/db/models.py` | every table of arch §4 (29), typed `Mapped[]`; class names: `User Account Goal IncomeSource FixedCost LifeEvent LifeProfile PlanPreferences Product SimClock Transaction DayLedger Plan Slip Reflection Transfer AgentEvent Message Notification AgentRun ToolCall LifeFact SpendingSignature PatternRule Receivable Pot GoalForecast CategoryBaseline Merchant` |
| Conventions | same file | money `NUMERIC(12,2)` (`Money`), scores `NUMERIC(5,4)`, JSONB, timestamptz **defaulting to `app.clock.now()`** (sim time, never the DB clock), enums as text + CHECK from `app.domain.enums` (`enum_check` / `enum_in`), constraint names `ck_/uq_/ix_/fk_<table>_…` |
| Session | `backend/app/db/session.py` | `get_db()` (FastAPI dependency), `unit_of_work()` (commit / rollback), `session_factory()`, `configure(url)` |
| Schema mgmt | `backend/app/db/init.py`, `migrations/`, `app/db/migration_helpers.py` | `upgrade(conn)`, `downgrade(conn)`, `drop_all(conn)`, CLI `python -m app.db.init [--reset]`; `replace_enum_check(table, column, Enum)` |
| Event dedup | `models.DAY_LEVEL_EVENT_TYPES`, `models.TRANSACTION_EVENT_TYPES` | `transaction_question` is unique per `(user, type, transaction)` and needs `ref_transaction_id`; **every other type is unique per `(user, type, event_date)`**, incl. `receivable_reminder` and `hypothesis_check` (one per day) |
| Cascades | all `user_id` FKs | `ON DELETE CASCADE`: deleting a user deletes everything it owns (`/sim/reset`); links between rows are `SET NULL`, except a fact's signatures, a run's tool calls, a goal's forecasts and a transaction's questions (CASCADE) |
| Test helpers | `backend/tests/factories.py` | `user`, `goal`, `transaction`, `everything` (one row in every per-user table) |

**Beyond the spec (all tested):** `users.city` and `agent_events.event_date` (both from Bomboe.md B2); **`goals.soft`** (bool, default `true`: the deadline may move; danutu's E9 offers "move the deadline" only for soft goals; second migration `56a08bb4ec07`, agreed by bomboe); `transfers` one auto-save per income transaction (D37 idempotency); `pots` one per goal; `life_facts` CHECK "temporary needs `valid_to`"; signatures `replacement_cycle_days > 0`; forecasts `p10 ≤ p50 ≤ p90`; `reflections.motivation` 1–5; `plan_preferences.buffer_pct` 0–0.3; `products.min_months ≤ max_months`; extra indexes `notifications(user_id, created_at)`, `life_facts(user_id, status)`, `receivables(user_id, status)`, `spending_signatures/pattern_rules(user_id, active)`, `goal_forecasts(user_id, computed_at)`.

### B5 · Auth (step 1 ✅ token verification; step 2 `current_user` etc. next)

| Piece | Where | Notes for others |
|---|---|---|
| `verify_token(token) -> Claims(sub, azp, roles, raw)` | `backend/app/auth.py` | RS256 only; `iss == KEYCLOAK_ISSUER`; `exp`/`nbf` with 30 s leeway **against real time** (tokens come from Keycloak's clock, not the simulator's); `azp` ∈ {savings-frontend, savings-dev, savings-cron} or `aud` ∋ `KEYCLOAK_AUDIENCE`. Errors: `invalid_token`, `token_expired`, `invalid_issuer`, `invalid_audience` (401), `auth_unavailable` (503) |
| `JWKSCache`, `get_jwks()`, `set_jwks()` | same | keys by `kid` from `<KEYCLOAK_INTERNAL_URL or KEYCLOAK_ISSUER>/.well-known/openid-configuration`; encryption keys ignored; an unknown `kid` refetches at most once per 60 s; Keycloak down → 503 only when the key isn't cached. Verified live against the running Keycloak (a Matei token and a cron token) |

### Service contract (stubs for danutu and David G.) ✅ signatures · bodies in B3/B4

| What | Where | Notes for others |
|---|---|---|
| Every service of arch 15.1 + Bomboe.md B3 | `backend/app/services/<group>.py` (25 modules) | **code against these now.** Bodies raise `NotImplementedError("B3 step n")` until B3 fills them; the signatures won't change |
| The full list (names + parameters) | `backend/tests/unit/test_service_contracts.py::CONTRACT` | read this first; changing it is a contract change (tell the others) |
| Rules | `app/services/__init__.py` docstring | every function takes `db, user_id` and only sees that user's rows (except `products`, `merchants`); another user's id → `DomainError("not_found", 404)`; bad state change → `invalid_transition` (409); returns `app.domain` objects, never ORM rows; **functions flush, the caller commits** |
| `load_user_context(db, user_id, today, history_days=180)` | `app/services/context_loader.py` | **stub returns `tests.builders.matei_ctx(today=today)` for any user** until B4 |
| Domain additions for the services | `app/domain/models.py` | `Product`, `LedgerDay`, `MessageView`, `NotificationView` |

Differences from the names in Bomboe.md / arch 15.1:
- `list(…)` → **`list_all(…)`** everywhere (a module function named `list` shadows the builtin inside the module); `ledger.range` → `ledger.between`.
- Added because the callers need them: `transactions.set_receivable`, `ledger.add_spent` (atomic delta for E3), `ledger.between`, `plans.save(db, user_id, result: PlanResult, *, reason, trigger_ref)` (E4 saves through it; the next version is assigned inside), `transfers.for_income` (auto-save idempotency), `messages.recent(limit=20)` (agent history), `notifications.unread_count`, `agent_runs.is_running`, `life_facts.list_all(status)`, `signatures.list_for_fact`, `pattern_rules.set_confidence` (C8), `pots.goal_pot`, `forecasts.weekly_history`, `life_profile.get/set_key/delete_key`, `life_events.mark_done`, `goals.get`.

---

## 4. Open questions & follow-ups

| # | For | Item |
|---|---|---|
| 1 | danutu | ✅ done: `goals.soft BOOL NOT NULL DEFAULT true` for E9. Seed: set `soft: false` in `profile.json` for fixed-date goals (e.g. Bianca's summer trip) |
| 2 | David G. | `merchants.json` / `products.json` need an `"id"` slug per entry (§1) |
| 3 | team | Q21: should the hosted demo run cron with `CRON_ENABLED_JOBS="process recover"`? |
| 4 | bomboe | B1 step 4 (local smoke script) after B6a (`/me`) and B8 (`/internal/process`) |
| 5 | bomboe | an empty `cashguard_db-data` volume is left on the native Docker engine (stack now runs on Docker Desktop); safe to delete |

---

## 5. Changelog

| Commit | What |
|---|---|
| `da088e8` | `api/` → `backend/`, root `.gitignore` |
| `90cea6e`, `7e333d9` | F1 minimal skeleton + enums; restored the arch doc ruff had reformatted |
| `82df875`, `cd7d4a1` | B1.1 compose skeleton |
| `42580c6` | B1.2 Keycloak on Postgres, realm seed |
| `4fe9bd5` | B1.3 cron container |
| `994b982` | B2.1 core tables, session, init; F3 db fixtures started |
| `457e697` | B2.2 money-flow tables |
| `ff0e8df` | B2.3 conversation tables |
| `02212e2` | B2.4 life-context tables, golden schema, cascades; **Alembic** migrations; `make check` → 228 passed |
| `6885c54` | `goals.soft` + migration `56a08bb4ec07`; `make check` → 230 passed |
| `f452337` | F3.1 `db_committed` fixture |
| `795cf23`, `7adce82`, `7a4e99d` | F2: money helpers, domain models + results, builders; `make check` → 320 passed |
| `c548bd1` | service contract: stubs of every B3 service + `load_user_context` stub; contract test |
| `c2d0ddd` | B5.1 `verify_token` + JWKS cache; F3 auth helpers |
| `34f1687` | F3.2–3 API + WS fixtures, `tests/README.md`; `make check` → 481 passed |
