# Work breakdown: every API task in detail

> **Scope:** the API only (`backend/`). The Flutter app is David V.'s and is separate for now (arch D39).
> **Source of truth for *what* to build:** [`savings-coach-backend-architecture.md`](savings-coach-backend-architecture.md) (v0.8). This file says *how*: files, functions, steps, edge cases, tests and "done when" for every task.
> **How we work on each task:** [`how-we-work.md`](how-we-work.md). **Short list for assigning:** [`../../TASKS.md`](../../docs/team/TASKS.md).
> Written 2026-10-28 by David G. with Claude. Sizes are rough hours **with Claude Code, including tests and review**.
> ✅ **Assigned 2026-10-28.** The working copies of these tasks, split into reviewable steps, are the per-person files [`Bomboe.md`](../../docs/team/Bomboe.md), [`Danutu.md`](../../docs/team/Danutu.md), [`DGAdavid1.md`](../../docs/team/DGAdavid1.md). This file is the overview. If the two differ, the architecture doc wins, then the per-person file, and fix the other.

---

## 0. Technical conventions (apply to every task)

### 0.1 Stack 🟡 (platform choices are bomboe's; these are the defaults unless he changes them)

| Concern | Choice |
|---|---|
| Python | 3.12, managed with **uv** (`backend/pyproject.toml`, `uv.lock` committed) |
| Web | FastAPI + Pydantic v2 + `pydantic-settings`; uvicorn, **1 worker** (in-memory WS manager) |
| DB | PostgreSQL 16, SQLAlchemy 2 **async** + psycopg 3; schema via `metadata.create_all` (no Alembic: the demo DB is reset anyway) |
| LLM | `anthropic` SDK, `AsyncAnthropic`, settings in arch 6.8 |
| Maths | numpy |
| Auth | PyJWT[crypto] + httpx (JWKS) |
| Tests | pytest, pytest-asyncio, pytest-cov, hypothesis (property tests), respx (mock httpx), jsonschema (schema checks), Starlette TestClient (WebSocket) |
| Quality | ruff (lint + format), mypy (strict on `app/domain`, `app/engine`, `app/context`) |

### 0.2 Folder layout (final)

```
backend/
├── pyproject.toml  uv.lock  .python-version  .env.example  Makefile  Dockerfile  docker-compose.yml  README.md
├── keycloak/realm-cashguard.json
├── cron/crontab  cron/run.sh
├── app/
│   ├── main.py  config.py  clock.py  errors.py  logging.py
│   ├── domain/      enums.py  money.py  models.py  results.py           ← shared types (F2), pure
│   ├── i18n/        labels.py  format.py  notifications.py              ← RO/EN texts (C1, B13)
│   ├── db/          models.py  session.py  init.py  seed.py
│   ├── services/    one module per table group + context_loader.py (B4)
│   ├── api/         schemas.py  me.py  state.py  chat.py  transactions.py  …  sim.py  internal.py
│   ├── ws.py  events.py
│   ├── pipeline/    processor.py  jobs.py  signals.py
│   ├── engine/      calendar.py  budget.py  ledger.py  stats.py  simulate.py  baselines.py  anomaly.py
│   │                forecast.py  options.py  savings.py  service.py (DB shells)
│   ├── context/     normalize.py  library.py  life_fit.py  evaluate.py  questions.py  rules.py
│   │                propagate.py  inference.py  calendar_events.py  products.py  service.py (DB shells)
│   ├── agent/       llm.py  tools.py  handlers/  executor.py  snapshot.py  prompts.py  style.py
│   │                templates.py  loop.py  proactive.py  fallbacks.py  language.py
│   └── sim/         clock_store.py  scenarios.py
├── data/            merchants.json  priors.json  products.json  signature_library.json  calendar.json
│                    personas/<id>/{config,profile,facts,transactions}.json  scenarios/<scene>.json
├── scripts/         generate_personas.py  placeholder_data.py  smoke_local.sh  smoke_remote.sh  (demo_client.py: planned, not written)
└── tests/
    ├── conftest.py  builders.py  fakes/fake_llm.py  fixtures/{db,api,auth,ws}.py
    ├── unit/        (pure: domain, engine, context, agent pieces)   marker: none (default)
    ├── db/          (needs Postgres)                                 marker: db
    ├── api/         (HTTP endpoints)                                 marker: api
    ├── ws/          (WebSocket)                                      marker: ws
    ├── acceptance/  (the demo numbers, pure: test_demo_numbers.py)   marker: none
    ├── golden/      (reviewed snapshots: prompts, snapshot text)
    └── eval/        test_llm_live.py  test_tools_live.py  test_onboarding_live.py   marker: live (real Claude, costs money)
```

### 0.3 Rules every task follows

1. **Functional core, imperative shell.** `engine/` and `context/` logic is **pure**: it takes `app/domain` objects plus `today`, returns `app/domain` results, and never touches the DB, the clock or the network. A thin `service.py` shell implements the §15 signatures (`db`, `user_id`, …): it loads data with `services.context_loader`, calls the core and saves the result. Almost every test targets the pure core, so tests are fast and need no database.
2. **Money** is `Decimal`, never `float`, outside the Monte Carlo internals. Round with `domain.money.to_money` (half-up, 2 decimals). Splits always add up exactly (`own + others == total`).
3. **Time** comes from `clock.today()` / `clock.now()` (shell only), in `Europe/Bucharest`. Cores receive `today` as a parameter. Never call `datetime.now()`.
4. **Every query is scoped by `user_id`.** Another user's id returns `not_found` (never `forbidden`: don't leak that it exists).
5. **Errors:** raise `DomainError(code, message)` with a stable `code` (listed in each task). The API maps it to the arch 9.1 error envelope.
6. **Texts** shown to users come only from `app/i18n` (RO + EN) or from Claude. Never hard-code user-facing strings elsewhere.
7. **Enum values** are exactly the strings in arch 4.4/4.5 (they're stored in the DB and sent in JSON).
8. **No secrets in git.** `.env` is ignored; `.env.example` lists every variable.

### 0.4 Test categories: run through this list for every task

| Category | Ask yourself |
|---|---|
| Happy path | Does the normal case give exactly the documented result? |
| Boundaries | Exactly at each threshold (0.55, 24h, 10%, 50 lei, month end, 180-day window)? One step either side? |
| Invalid input | Wrong type, missing, negative, zero, empty, too long, unknown enum? |
| Error paths | Dependency fails (DB, LLM, JWKS)? Partial failure in a batch? |
| Security | Another user's ids? Missing or forged token? Prompt injection in text fields? |
| Concurrency | Two runs for the same user at once? Double submit? |
| Idempotency | Run twice: same state, no duplicates? |
| Time | Sim clock, Bucharest midnight, DST (2026-10-25), short months, leap years, weekday rules? |
| Money | Decimal exactness, rounding, splits that add up, no negative effective amounts? |
| Language | RO and EN, with and without diacritics? |
| Personalisation | Same input, different persona → different, correct result? |
| Invariants (property tests) | What must *always* hold (ranges, sums, monotonicity)? Write a hypothesis test. |
| Performance | Is there a budget (ms) in the arch doc? Assert it with a margin. |
| Regression | Is there a golden value / reviewed snapshot that must not drift silently? |

---

## 1. Dependencies and the critical path

```
F1 ─► F2 ─┬─► C1 ─► C2 ─────────────┐
          ├─► C4 ─► C5 ─► C6 ─► C7 ─┼─► A3 ─► A6 ─► A7 ──┐
          ├─► E1 ─► E2 ─► E4        │    ▲               │
          │    E6 ─► E7 ────────────┘    │               │
          │    E8 ─► (E9)                A1, A2, A4, A5  │
          │    E10, E3                                   ▼
          └─► B2 ─► B3 ─► B4 ─► B8 ─► B9, B10 ─► D4 ─► ★ CHECKPOINT (Scene A)
F1 ─► B1 ─► F3 ─► (all db/api tests)   B5, B7 ─┘   E12 + D1 + D2 ─► B12 ─┘
```

**Critical path to the checkpoint (Scene A end-to-end):** F1 → F2 → B2 → B3 → B4 → B8 → B9/B10 → D4, in parallel with C1 → C2 → C4 → C5 → C6 → C7, E1 → E2/E6/E7/E8/E10/E3/E4, A1 → A2 → A3 → A6 → A7, and E12 + D1 + D2 → B12.
**Stubs unblock parallel work:** in hour 0–1 every owner commits stubs of their §15 functions returning fixtures (arch §15).

---

## 2. Foundations (F)

### F1 · Repo skeleton & tooling · S 0.5h · P0 · deps: — · suggested: David G.
**Goal.** A runnable, testable empty app that everyone builds on.
**Files.** `pyproject.toml` (deps from 0.1; dev group), `.python-version`, `.env.example` (every var from arch §3), `Makefile` (`dev`, `test`, `test-all`, `check`, `db-up`, `fmt`), `app/main.py` (`create_app()` factory, router mount at `/api`, `/api/health`), `app/config.py` (`Settings`), `app/clock.py`, `app/errors.py`, `app/logging.py`, `backend/README.md` (run locally), `.gitignore` additions (`.env`, `.venv`, `__pycache__`, `.pytest_cache`, `.coverage`).
**Steps.**
1. `uv init` / write `pyproject.toml`; tool configs for ruff, mypy, pytest (markers `db`, `api`, `ws`, `live`, `slow`; default `-m "not live"`).
2. `Settings` (pydantic-settings): every env var; `SIM_MODE: bool`, `SIM_START_DATE: date`, `ANTHROPIC_API_KEY: SecretStr | None`.
3. `clock.py`: a `Clock` protocol with `today()`, `now()`; `RealClock` (Bucharest tz), `FixedClock` (tests); a module-level `get_clock()` / `set_clock()` (B10 adds `SimClock`).
4. `errors.py`: `DomainError(code, message, status=400)`; handlers for `DomainError`, `RequestValidationError` (422) and any `Exception` (500, generic message, no stack trace) → arch 9.1 envelope.
**Tests.**
- unit: `Settings` reads env and `.env`; `SIM_MODE` accepts `true/1/false/0`; a missing optional key is `None`.
- unit: `FixedClock` returns its date; `RealClock.now()` is tz-aware Bucharest; at `2026-06-14T21:30Z` `today()` is `2026-06-15` (UTC+3); on the DST day (2026-10-25) `today()` is correct before and after 04:00 local.
- api: `GET /api/health` → 200 `{"status":"ok"}`; unknown route → 404 in the envelope; a test route raising `DomainError("x_code")` → its status + envelope; bad body → 422 envelope; a route raising `RuntimeError` → 500 envelope with no stack trace in the body.
- tooling: `make check` (ruff + mypy + unit tests) passes on the empty project.
**Done when.** `uv sync && make check` is green; `backend/README.md` explains how to run.

### F2 · Shared domain types & enums (`app/domain/`) · M 1h · P0 · deps: F1 · suggested: David G. (danutu reviews)
**Goal.** One set of typed objects used by every pure core, so teams never exchange loose dicts.
**Files.** `app/domain/enums.py`, `money.py`, `models.py`, `results.py`; `tests/builders.py`.
**Content.**
- `enums.py` (`StrEnum`, values exactly as in the arch doc): `Category`, `Purpose`, `Beneficiary`, `Decision`, `Direction`, `FactType`, `FactStatus`, `FactSource`, `Persistence`, `SignatureEffect`, `SignatureOrigin`, `RuleKind`, `RuleSource`, `ReceivableStatus`, `PotKind`, `PotStatus`, `AnnotationSource`, `InputMode`, `AgentEventType`, `AgentEventStatus`, `Language`, `CoachStyle`, `TransferKind`, `ProductKind`, `Liquidity`.
- `money.py`: `to_money(x) -> Decimal` (from `str(x)`, half-up, 2 dp), `split_share(total, people) -> (own, others)`, `share_each(others, n)`.
- `models.py` (Pydantic v2, `frozen=True`): `Item`, `TxView`, `LifeFact` (+ typed `value` per `FactType`: `OccupationValue`, `HouseholdMemberValue`, `PetValue`, `VehicleValue`, `ActivityValue`, `PriorityValue`, `LifeEventValue`, `CustomValue`…), `Signature`, `RuleMatch`, `RuleOutcome`, `PatternRule`, `Receivable`, `Pot`, `Goal`, `IncomeSource`, `FixedCost`, `LifeEvent`, `PlanPreferences`, `Baseline`, `Merchant`, `UserProfile`, `AgentEventView`, `UserContext` (the aggregate in B4).
- `results.py`: `Evaluation`, `QuestionHint`, `FitResult`, `AnomalyFeatures`, `DayBudget`, `PlanResult`, `PlanSummary`, `Forecast`, `Driver`, `Option`, `SimResult`, `QuestionCandidate`, `RuleChange`, `PropagationResult`.
- `tests/builders.py`: `tx(...)`, `fact(...)`, `signature(...)`, `rule(...)`, `ctx(...)` with sensible defaults, plus `matei_ctx()`, `andrei_ctx()`, `bianca_ctx()`, `ioana_ctx()` (small, hand-made, for unit tests; the big seeded data comes from E12).
**Validation rules (put in the models).** `0 ≤ effective_amount ≤ amount`; `amount > 0`; `household_member` needs `role ∈ {adult, child}` and a child needs `age`; `occupation` needs `title`; `valid_to ≥ valid_from`; `temporary` needs `valid_to`; signature `amount_min ≤ amount_max`, `0 ≤ strength ≤ 1`, `multiplier > 0`, `explains` needs a category or merchant hints, `expects_event` needs `expected_amount` and a date or months; rule `from < to`, weekdays 1–7 (ISO); timestamps tz-aware.
**Tests.**
- golden: each enum's value list equals the list in arch 4.4/4.5 (a rename breaks loudly).
- `to_money`: `"1.005"` → `1.01`; `1.005` (float) → `1.01` (via `str`); `-2.675` → `-2.68`; `7` → `7.00`.
- `split_share`: (500, 5) → (100, 400); (500, 3) → (166.67, 333.33), sum 500 exactly; (100, 1) → (100, 0); (0.01, 3) → (0.00, 0.01); people 0 or negative → `ValueError`; negative total → `ValueError`. `share_each(333.33, 2)` → 166.67 (display only; the total stays 333.33).
- property: for any total 0.01–100000 and people 1–50, `own + others == total` and both ≥ 0.
- every validation rule above: one passing and one failing case each.
- frozen: assigning to a field raises; JSON round-trip (`model_dump(mode="json")` → `model_validate`) gives an equal object; Romanian diacritics and emoji survive.
- builders produce valid objects.
**Done when.** `mypy --strict app/domain` is green; both AI owners agree the types cover their cores.

### F3 · Test infrastructure (DB, API, auth, WS fixtures) · M 1h · P0 · deps: F1, B1, B2 · suggested: bomboe
**Goal.** Writing a db/api/ws test takes one fixture.
**Files.** `tests/conftest.py`, `tests/fixtures/{db,api,auth,ws}.py`, `tests/README.md`; `db-test` service in compose (port 5435, tmpfs).
**Content.**
- `db`: session-scoped async engine on `TEST_DATABASE_URL`; `drop_all` + `create_all` once per session; function-scoped session inside an outer transaction with a nested SAVEPOINT, rolled back after each test. `db_committed`: real commits, `TRUNCATE … CASCADE` afterwards (for pipeline concurrency tests).
- `auth`: an RSA keypair per session; `make_token(sub, roles=(), exp_in=300, iss=…, azp=…, alg="RS256", kid=…)`; the app's JWKS fetcher overridden to return the test public key.
- `api`: `client` = `httpx.AsyncClient(transport=ASGITransport(app))`; `as_user(user)` adds the Bearer header.
- `ws`: Starlette `TestClient` helper `ws_connect(user)`.
- `seeded_db`: loads the seeded personas once per session into a template database (fast reuse).
**Tests (of the fixtures).** A write in test A is invisible in test B; `db_committed` leaves empty tables; a `make_token` token validates with the app's validator and an `exp_in=-1` token doesn't.
**Done when.** Documented in `tests/README.md` with one example per fixture.

---

## 3. Backend platform (B)

### B1 · docker-compose, env & Keycloak realm · S 0.75h · P0 · deps: F1 · suggested: bomboe
**Files.** `docker-compose.yml` (`db` postgres:16, `db-test`, `keycloak` pinned version with `--import-realm`, `api`, `cron`), `Dockerfile`, `keycloak/realm-cashguard.json`, `cron/crontab`, `cron/run.sh` (client-credentials token → `curl` the internal endpoint), `scripts/smoke_local.sh`.
**Realm.** Clients `savings-frontend` (public, PKCE, redirect `ro.cashguard.app:/oauthredirect` + `http://localhost:*`), `savings-cron` (confidential, service account, realm role `internal`), `savings-dev` (direct access grants, dev/test only). Users `matei`, `andrei`, `bianca`, `ioana`, `alex` with fixed ids (= `keycloak_sub` in the seed). Access token lifespan ≥ 30 min.
**Tests.**
- unit: parse the realm JSON → the 3 clients exist with the right flags; redirect URIs present; 5 users with the expected ids; token lifespan ≥ 1800 s; `savings-cron` has role `internal`.
- smoke (`scripts/smoke_local.sh`): compose up → health 200 → password-grant token for `matei` via `savings-dev` → `/api/me` 200 → cron token → `/api/internal/process` 2xx.
**Done when.** One command brings everything up and the smoke script passes.

### B2 · Database models (all tables) · M 1.5h · P0 · deps: F1, F2 · suggested: bomboe
**Files.** `app/db/models.py` (SQLAlchemy 2 typed `Mapped[]`), `app/db/session.py` (async engine, sessionmaker, `get_db`, `unit_of_work()`), `app/db/init.py`.
**Content.** Every table and column of arch 4.1, 4.2 (incl. `transfers.kind/pot_id/income_transaction_id`) and 4.4 (incl. the column additions). Enums stored as `String` + `CHECK (col IN (…))` built from the F2 enums. Money `NUMERIC(12,2)`, `JSONB`, `timestamptz`.
**Constraints & indexes.** `users.keycloak_sub` UNIQUE; partial unique `goals(user_id) WHERE status='active'`; `plans` UNIQUE `(user_id, version)`; `day_ledger` PK `(user_id, date)`; `agent_events`: a stored `event_date` + partial unique `(user_id, type, event_date)` for day-level types and `(user_id, type, ref_transaction_id)` for transaction types; `category_baselines` PK `(user_id, category)`; `transactions` CHECK `amount > 0` and `0 ≤ effective_amount ≤ amount`. Indexes: `transactions(user_id, status)`, `transactions(user_id, occurred_at)`, `agent_events(user_id, status)`, `messages(user_id, created_at)`, `life_facts(user_id, status)`, `spending_signatures(user_id, active)`, `goal_forecasts(user_id, computed_at)`.
**Tests (db).**
- `create_all` on an empty DB, then `drop_all`, both succeed.
- golden: the table/column list equals the list derived from arch §4 (a missing column fails the test).
- every CHECK: invalid enum value, `effective_amount > amount`, `amount ≤ 0` → `IntegrityError`.
- second active goal → error; a completed goal + an active one → ok.
- duplicate plan version, duplicate ledger day → error.
- agent_events: two `overspend` on the same date → error; two `transaction_question` for different transactions on the same date → ok; the same transaction twice → error.
- `Decimal('0.30')` round-trips exactly; JSONB with `ă î ș ț` and emoji round-trips; `timestamptz` keeps the instant.
- deleting a user removes its dependent rows (used by `/sim/reset`), or the explicit delete order is tested.
**Done when.** The schema matches arch §4 exactly.

### B3 · CRUD services · M 1.5h · P0 · deps: B2 · suggested: bomboe
**Files.** `app/services/*.py`, one module per table group (users, accounts, goals, income_sources, fixed_costs, life_events, transactions, ledger, plans, slips, reflections, agent_events, messages, notifications, products, life_facts, signatures, pattern_rules, receivables, pots, transfers, forecasts, baselines, plan_preferences, agent_runs, tool_calls).
**Rules.** Every function takes `user_id` and filters by it (except `products`); reads return F2 domain objects; writes validate state transitions; `not_found` for other users' rows.
**Functions the others rely on (arch 15.1).** `transactions.get / list_effective(user_id, since, until, category=None) / save_evaluation(tx_id, Evaluation) / annotate(...) / set_pot`; `life_facts.create / update / expire / delete / list_active(on_date) / list_hypotheses / confirm / reject`; `signatures.replace_for_fact` (atomic) `/ list_active(effect=None)`; `pattern_rules.create / list_active / record_hit / record_miss / deactivate`; `receivables.create / update_status / cancel / list_open`; `pots.create / update / close / list_active / add_saved`; `agent_events.create / mark_asked / mark_answered / expire / pending_for / question_asked_today(user_id, date)`; `messages.save_user / save_assistant(...)`; `forecasts.latest / last_weekly_snapshot`; `transfers.create / undo`.
**State machines.** agent_events `pending → asked → answered | expired`, `pending → handled | expired`; receivables `open → requested → paid`, `open|requested → cancelled`; life_facts `hypothesis → confirmed | rejected`, `confirmed → expired`; transfers undo once.
**Tests (db).**
- per module: create → get → list → update → delete.
- isolation: for every module, user B reading or writing user A's row → `not_found`.
- `messages.list(since)` is exclusive and ordered oldest first; `limit` respected.
- `list_effective` excludes `unresolved` and `failed`; date bounds inclusive (documented).
- `question_asked_today` counts only question types, by `asked_at` on that Bucharest date (23:59 vs 00:01 boundary).
- every valid transition works; every invalid one raises (`invalid_transition`).
- `pots.add_saved` can't go below 0; transfer undo twice → `already_undone`.
- rejected facts are absent from `list_active`; an expired fact is absent after `valid_to`.
- `signatures.replace_for_fact` is atomic (a failure in the middle leaves the old set).
**Done when.** Arch 15.3's service checklist is all ticked.

### B4 · Read model `load_user_context` · S 0.75h · P0 · deps: B3, F2 · suggested: bomboe (David G. reviews: it's the AI's view of the world)
**Interface.** `async def load_user_context(db, user_id: int, today: date, history_days: int = 180) -> UserContext`.
**Content.** Profile (language, coach_style, household_scale, city), account, active goal + goal pot, income sources, fixed costs, planned life events, active pots, open/requested receivables, confirmed facts active on `today` + hypotheses (separate list), active signatures, active rules, plan preferences, cached baselines, resolved transactions of the last 180 days as `TxView`, latest plan summary, latest forecast + last weekly snapshot, pending/asked agent events, question budget used today.
**Tests (db).**
- seeded Matei → counts match the seed files.
- a fact with `valid_to < today` is excluded; a rejected fact is excluded; hypotheses come in their own list.
- transactions older than 180 days, `unresolved` or `failed` are excluded.
- two users seeded → the other user's data never appears.
- query count ≤ 10 (SQLAlchemy statement counter) and < 50 ms for the biggest persona.
- the result is immutable.

### B5 · Auth: JWT validation, `current_user`, internal role, WS token · M 1h · P0 · deps: F1, B3 · suggested: bomboe
**Files.** `app/auth.py`: `JWKSCache` (discovery → `jwks_uri`, keys cached; on an unknown `kid` refetch at most once per 60 s), `verify_token(token) -> Claims` (RS256 only; `iss == KEYCLOAK_ISSUER`; `exp`, `nbf` with 30 s leeway; `azp` in the allowed clients or `aud` contains `KEYCLOAK_AUDIENCE`), `current_user` dependency (`sub` → `users.keycloak_sub`), `require_internal`, `ws_user(token)`.
**Error codes.** `missing_token`, `invalid_token`, `token_expired`, `invalid_issuer`, `invalid_audience`, `unknown_user` (all 401); `forbidden` (403); `auth_unavailable` (503 when JWKS can't be fetched and nothing is cached).
**Tests.**
- valid token → user; expired → `token_expired`; `nbf` in the future → 401; wrong `iss` (e.g. `http://10.0.2.2:8080/realms/cashguard`) → `invalid_issuer`; wrong `azp`/`aud` → `invalid_audience`.
- `alg: none` → 401; HS256 signed with the public key as secret (algorithm confusion) → 401.
- unknown `kid` → one refetch → still unknown → 401; JWKS down with an empty cache → 503; down with a warm cache → still validates.
- no header / `Bearer` with no token → `missing_token`; lowercase `bearer` accepted.
- internal endpoint with a user token → 403; with role `internal` → ok.
- WS with a bad token → closed with 1008.
- a valid `sub` that isn't in the DB → `unknown_user`.

### B6a · REST core endpoints · M 1h · P0 · deps: B3, B4, B5 (E4, E8 shapes; stubs ok) · suggested: bomboe
**Endpoints.** `GET/PATCH /me`, `GET /state`, `GET /messages`, `GET /notifications`, `POST /notifications/{id}/read`, `GET /plan`, `GET /plan/history`, `GET /transactions`, `GET /transactions/{id}`, `PATCH /transactions/{id}`, `POST /transfers/{id}/undo`. Response models in `app/api/schemas.py` exactly as arch 9.3.
**Serialisation.** Money → JSON number rounded to 2 dp; dates `YYYY-MM-DD`; timestamps ISO-8601 UTC with `Z`.
**Tests (api).**
- every endpoint: 200 with a body that validates against its schema and has the keys of the 9.3 example; 401 without a token; 404 for another user's id.
- `/state` before onboarding → `goal`, `plan`, `forecast` are `null`; `pending_question` is set while a question is open and `null` after the answer.
- `/messages?since=` exclusive, `limit` respected; `/notifications?unread_only=true`.
- `PATCH /transactions/{id}`: `own_amount > amount` → 422 `invalid_own_amount`; `people_count = 0` → 422; a valid patch → new plan version + WS `transaction.annotated` (push mocked).
- `PATCH /me` with `language = "fr"` → 422.
- `POST /transfers/{id}/undo` twice → 409 `already_undone`.
- **route-table test:** iterate `app.routes`; every `/api` route except `/health` (and `/sim/*` when enabled) returns 401 without a token.

### B6b · REST context endpoints · M 1h · P1 (request-payment is P0) · deps: B3, C4, C9 · suggested: bomboe
**Endpoints.** `GET /forecast`, `GET /receivables`, `POST /receivables/{id}/request-payment | mark-paid | cancel`, `GET /pots`, `GET/POST /life-facts`, `PATCH/DELETE /life-facts/{id}`, `POST /life-facts/{id}/confirm | reject`, `GET /products`, `GET /life-profile`, `PATCH/DELETE /life-profile/{key}` (soft notes only).
**Tests (api).**
- `request-payment`: status → `requested`, a notification "Cerere trimisă: 4 × 100 lei" (RO) / EN equivalent, WS `receivable.updated`; a second call → 409 `invalid_transition`.
- `mark-paid` → `paid` + plan recompute (expected receivables drop, the balance is unchanged until the money arrives).
- `POST /life-facts` with an invalid type/value → 422; a valid one → signatures created, baselines + plan recomputed (propagation mocked in the api test, real in one integration test).
- `DELETE /life-facts/{id}` removes its signatures; `confirm` → `confirmed`; `reject` → `rejected` and never proposed again.
- `/products` is ranked (C12), with `why_for_you` in the user's language.
- isolation + 401 for every route.

### B7 · WebSocket ConnectionManager & events · S 0.75h · P0 · deps: B5 · suggested: bomboe
**Files.** `app/ws.py` (`ConnectionManager`: `dict[user_id, set[WebSocket]]`, `connect / disconnect / push`; `/ws?token=`; ping every 30 s; envelope `{type, data, ts}`; `push_after_commit(session, user_id, event)` registered on the session's `after_commit`), `app/events.py` (one builder per event in arch 5.2).
**Tests (ws).**
- valid token → accepted; invalid → closed 1008.
- a push to user A reaches every socket of A and none of B.
- disconnect removes the socket; a push to a user with no sockets doesn't raise; a socket that dies mid-push is removed and the others still receive.
- `push_after_commit`: rollback → no event; commit → exactly one event.
- `ts` is ISO UTC `Z`; every builder's payload keys equal the arch 5.2 table (golden).
- ping arrives (interval shortened in the test).

### B8 · Ingestion & processing pipeline · M 1.5h · P0 · deps: B3, B7 (C6, E3, E4, E8, E10, C7 as stubs) · suggested: bomboe
**Files.** `app/services/ingest.py` (`ingest(db, user_id, TxIn) -> tx_id`), `app/pipeline/processor.py` (`process_user(user_id, trigger)` exactly as arch F3 v0.8), `app/api/internal.py` (`/internal/process`, `/internal/recover`).
**Rules.** `pg_advisory_lock(user_id)`; claim with `FOR UPDATE SKIP LOCKED`; each transaction in its own SAVEPOINT (one failure doesn't undo the others); **evaluate before apply**; salary credit → `engine.auto_save`; plan + forecast recomputed **once per batch**; pick_question → at most one `transaction_question`; proactive run only if `trigger != "chat"`; every push after commit.
**Ingest validation.** `amount > 0`; `direction ∈ {debit, credit}`; `items` well-formed; `occurred_at` not later than sim today + 1 day; `merchant_raw` 1–200 chars → `invalid_transaction`.
**Tests (db_committed, with spies on the stubs).**
- 3 unresolved → all resolved; the ledger uses effective amounts.
- call order per transaction: evaluate → save_evaluation → apply → push.
- evaluate raises for tx #2 → #2 has `attempts = 1` and stays `unresolved`; #1 and #3 resolved. The third failure → `failed` with the error text.
- `/internal/recover` resets only `processing` rows older than 5 min.
- two `process_user` for the same user at once (`asyncio.gather`) → each transaction applied exactly once, balance correct.
- nothing to process → no plan version bump, no events.
- a salary credit triggers `auto_save` once; re-running doesn't double it.
- `pick_question` returns a candidate → exactly one agent_event; the proactive run is called for `sim`/`cron` and **not** for `chat`.
- push happens after commit (order check); a rollback sends nothing.
- a late transaction for a past day updates that day's ledger.
- every ingest validation rule: one reject case each.

### B9 · Chat endpoint & agent run orchestration · S 0.75h · P0 · deps: B3, B7 (A6 stub) · suggested: bomboe
**Files.** `app/api/chat.py`.
**Flow.** `POST /chat {text, input_mode}` → validate (strip, 1–2000 chars, `input_mode` enum) → per-user busy check (in-memory set + `agent_runs.status = running` as the truth after a restart) → save the user message + language update (A11) → 202 → background: push `agent.typing` → `process_user(trigger="chat")` → `run_agent` → save the assistant message (quick replies, action cards, speak, speak_text, refs) → push `assistant.message` → after-run hooks (`plan.updated` once, `forecast.updated`). On any exception → fallback message in the user's language, run marked failed, busy cleared.
**Tests (api + ws).**
- 202 returns `message_id` and `run_id`; the message is stored with its `input_mode`.
- a second POST while running → 409 `agent_busy`; after completion → accepted again.
- empty text or > 2000 chars → 422; unknown `input_mode` → 422.
- WS order: `agent.typing` → `assistant.message`; `plan.updated` only if the plan changed.
- `run_agent` raises → fallback text saved and pushed, run `failed`, busy cleared.
- an English message switches `users.language` to `en`.

### B10 · Simulator · M 1h · P0 · deps: B8, B12 (B11 for the day jobs) · suggested: bomboe
**Files.** `app/api/sim.py`, `app/sim/clock_store.py` (`SimClock` backed by `sim_clock`, cached in process), `app/sim/scenarios.py` (loads `data/scenarios/*.json`).
**Endpoints.** `next-day`, `jump {days}`, `reset`, `transaction {scenario_id | raw}`, `personas`. All return **404 when `SIM_MODE=false`** and are left out of the OpenAPI schema.
**Semantics.** `next-day`: insert that day's scripted transactions → process → close-day → advance the clock → day jobs in the order of arch §10. `reset`: delete all user data → reseed → clock = `SIM_START_DATE` → push `plan.updated` to connected users. `transaction`: inject one transaction for the caller (or a `persona` param) and run F3 immediately.
**Tests.**
- `next-day` advances exactly one day and runs the jobs in the documented order (spy); `clock.today()` inside the pipeline equals the new sim date.
- `jump 5` → 5 days; crossing a Monday takes the weekly snapshot once.
- `reset` → row counts equal a fresh seed; clock = 2026-06-15; running it twice gives the same result.
- unknown scenario → 404 `scenario_not_found`; a bad raw payload → 422; `transaction` returns the id and the transaction is already resolved.
- `SIM_MODE=false` → every `/sim/*` route is 404 and absent from `/openapi.json`.

### B11 · Day jobs, internal endpoints & cron · M 1h · P1 · deps: B8, E11, C7 · suggested: bomboe
**Files.** `app/pipeline/jobs.py`: `close_day`, `weekly_reflection`, `preemptive`, `expire_events` (pending > 48 h), `expire_questions` (asked > 24 h → `context.default_reading`), `receivable_reminders` (open > 14 days), `forecast_snapshot` (Monday), `infer_hypotheses` (Sunday); one internal endpoint per job (`require_internal`); `cron/crontab` as arch §10.
**Tests.**
- each job is idempotent per (user, date).
- close-day status thresholds (from E11): ok / warning / overspent / under, tested exactly at each boundary.
- `expire_questions`: asked 23h59m ago → untouched; 24h01m ago → default annotation (`unplanned_discretionary`, confidence 0.3, source `default`) + event `expired`; an answered question is never touched.
- an overspend question is created only if today's question is free; otherwise a quiet notification is sent instead.
- internal endpoints without the role → 403.

### B12 · Seed loader · S 0.75h · P0 · deps: B2, B3, E12, D1, C4 · suggested: danutu (he owns the data)
**Files.** `app/db/seed.py` (`seed_all`, `seed_persona`), CLI `uv run python -m app.db.seed --reset`.
**Loads.** Users (ids from the realm JSON), accounts, income, fixed costs, goal + goal pot, pots, facts + signatures (via `signatures_for_fact`), seeded rules, history transactions (status `resolved`, annotations from the generator), merchants, products, `sim_clock`. Then runs `recompute_baselines` → `recompute_plan` → `forecast_goal` once per persona, plus the "last week" forecast snapshot.
**Tests (db).**
- seeding twice with `--reset` gives the same counts.
- each persona exists with the right `keycloak_sub`; Matei's balance equals `profile.json`.
- Matei's Friday rule is present at 0.7 with 2 hits; Andrei's occupation fact has `work_tool` signatures; Ioana's `household_scale` is 2.1.
- baselines exist (Matei groceries median 85 ± 10); a plan and a forecast exist per persona; Matei's last weekly snapshot ≈ 0.72.

### B13 · Notifications service & templates · S 0.5h · P1 · deps: B3, C1, A5 · suggested: bomboe
**Files.** `app/services/notifications.py` (`notify(user, type, params)`), `app/i18n/notifications.py` (RO + EN templates: overspend, plan_updated, streak/milestone, auto_save, payment_request_sent, receivable_reminder, goal_completed).
**Number format** (shared `app/i18n/format.py` from C1): RO `10.000 lei`, `30,40 lei`; EN `10,000 lei`, `30.40 lei`.
**Tests.** Every template exists in RO and EN and fills its params; no template contains a banned phrase (A5 checker over all of them); `opens_chat` set as designed per type; `notification.new` pushed after commit.

### B14 · Hosting & deploy · M 1h · P0 (before the freeze) · deps: B1 · suggested: bomboe
**Content.** A VM with Docker; a reverse proxy with automatic TLS (e.g. Caddy) in front of the API and Keycloak; `KC_HOSTNAME` = Keycloak's public HTTPS URL = `KEYCLOAK_ISSUER`; Keycloak proxy headers enabled; secrets only on the server; uvicorn 1 worker; cron container; `SIM_MODE=true`.
**Tests.** `scripts/smoke_remote.sh <base>`: health, token via `savings-dev`, `/me`, WSS connect + ping through the proxy, `/sim/reset`, then Scene A with the demo client (D4). Run after every deploy.

### B15 · Audit logging (agent_runs, tool_calls) & privacy · S 0.5h · P1 · deps: B3, A6 · suggested: bomboe
**Tests.** Every run writes an `agent_runs` row (trigger, model, iterations, status, error); every tool call writes a `tool_calls` row (input, output, status); **no system prompt or full transcript is stored** (Q27); the API key never appears in captured logs.

---

## 4. Engine & calculations (E)

### E1 · Calendar utilities · S 0.5h · P0 · deps: F2 · suggested: danutu
**Files.** `app/engine/calendar.py`: `occurrences(day_of_month, start, end)` (day 31 → last day of shorter months), `paydays_between`, `months_between`, `days_in_month`, `iter_days(start, end)`, `next_monday(d)`. Every function documents whether bounds are inclusive.
**Tests.** Day 31 in Feb 2027 → Feb 28; day 29 in Feb 2028 → Feb 29; day 30 in Feb 2027 → Feb 28; `start == end`; `end < start` → empty; `iter_days` across 2026-10-25 (DST) has no gap and no duplicate; property: results inside the range, sorted, unique.

### E2 · Budget engine core (daily budget) · L 1.5h · P0 · deps: E1, F2 (E6, E10 stubs) · suggested: danutu
**Files.** `app/engine/budget.py`: pure `compute_plan(inputs: PlanInputs, today) -> PlanResult` implementing arch 6.7 (the definitions table, weights, pins, buffer, essentials floor, feasibility) and returning today's budget, `next_7_days`, `feasible`, infeasible days.
**Decisions to write down in code + tests.** Income dated today is already in the balance once processed, so occurrences start tomorrow. Fixed costs whose day has passed this month are paid. The rounding residual of the daily split goes to the last day, so the sum is exact. No goal → `None`. Deadline passed → `DomainError("deadline_passed")`.
**Tests.**
- a golden Matei plan (values fixed after the first calibration, then exact).
- property: changing weights never changes Σ budgets over the horizon; Σ budgets == rest_money exactly.
- a pinned day gets exactly the pinned amount; Σ unpinned = free − pinned total; pinned total > free → infeasible.
- an unpinned day below the essentials floor → infeasible, and the result lists those days.
- buffer 0 vs 0.1 → free money differs by exactly 0.1 × available.
- rent due later this month is counted; rent already due earlier this month isn't.
- an event covered by a pot is not subtracted twice.
- receivables: 400 open, not overdue → +360; 4 weeks overdue → +280; `expected_by` after the deadline → 0.
- deadline today → 1-day horizon; goal already reached → still_to_save 0; negative balance → infeasible, no crash.
- determinism; Decimal outputs at 2 dp; 200-day horizon < 5 ms.

### E3 · apply_transaction & ledger (incl. re-annotation deltas) · M 1h · P0 · deps: F2, B3 · suggested: danutu
**Files.** `app/engine/ledger.py` (pure `apply`, `reannotate_delta`), shells `apply_transaction(db, user_id, tx_id)` and `on_annotation_changed(db, user_id, tx_id, old, new)` (called by `annotate_transaction` and `PATCH /transactions`).
**Rules.** The balance moves by the full `amount` (debit −, credit +). Day "spent" counts `effective_amount` unless the purpose is `planned_event` or the transaction matches a fixed cost. Credits are never "spent". A pot-funded transaction reduces `pot.saved` by `amount`. The ledger date is `occurred_at` in Bucharest time.
**Tests.**
- debit 500 → balance −500, spent +500 (provisional).
- re-annotation 500 → 100 → spent −400, balance unchanged; → `planned_event` → spent −effective and `pot.saved` −amount.
- salary credit → balance +, spent unchanged; rent → not in spent.
- applying an already-resolved transaction is a no-op (guarded).
- a ledger row is created if missing; `23:30Z` in June lands on the next Bucharest day.

### E4 · recompute_plan, versions & reason · S 0.5h · P0 · deps: E2, B3 · suggested: danutu
**Files.** `app/engine/plans.py` shell: load context → `compute_plan` → save `plans` (version + 1, payload, feasible, reason, trigger_ref) → `PlanSummary(compare_to_previous=True)`.
**Tests (db).** Versions 1, 2, 3; two concurrent recomputes → versions 2 and 3 with no unique-constraint failure (lock or retry); `previous_today_budget` equals the previous version's; reason + trigger_ref stored; no goal → no row and `None`.

### E5 · simulate_plan & solve mode · M 1h · P1 · deps: E2, E8 · suggested: danutu
**Files.** `app/engine/simulate.py`: pure `simulate(inputs, changes) -> SimResult` on a copy (all change types of arch 6.7) + probability (2 000 paths for speed); solve by binary search: the earliest deadline giving ≥ target budget (monotonic), and the largest goal for the same deadline.
**Tests.** Nothing is saved (row counts unchanged); each change type moves the result in the right direction; solve returns the earliest valid deadline and the day before it is invalid; impossible target → `null` + reason; target ≤ current → the current deadline; `diff_vs_current` correct; a negative `est_cost` → `DomainError`; "no changes" → probability equal to the current forecast (same seed/paths).

### E6 · Baselines & household scale · M 1h · P0 · deps: F2, C1 (priors) · suggested: danutu
**Files.** `app/engine/baselines.py`: pure `household_scale(facts, on_date)` (OECD 1 / 0.5 / 0.3; a child is under 14; temporary members only inside their window), `compute_baselines(txs, priors, scale, city, today)` (median + MAD on effective amounts of the last 180 days; `planned_event` and "not me" excluded; blend k = 5; monthly expected; MAD fallback), `essentials_floor(baselines, month)`, `rescale(...)`; shell `recompute_baselines` writes `category_baselines` + `users.household_scale`.
**Tests.**
- scale: alone 1.0; couple 1.5; 2 adults + kids 7 and 11 → 2.1; a 14-year-old counts 0.5; a temporary adult in July → 2.6 on 2026-07-10, 2.1 on 2026-08-01; pets don't change it.
- blend: n = 0 → prior × scale × city; n = 5 → the midpoint; n = 100 → ≈ personal.
- MAD = 0 → 0.25 × median; only household categories are scaled (electronics isn't); unknown city → index 1.0.
- a 500 lei shared purchase counts as its 100 effective; the 180-day bound is inclusive.
- property: baselines ≥ 0; scale ≥ 1 whenever there is an adult.

### E7 · Anomaly features · S 0.5h · P0 · deps: E6 · suggested: danutu
**Files.** `app/engine/anomaly.py`: pure `anomaly_features(tx, baseline, history, monthly_disposable) -> AnomalyFeatures` (arch 5.3.4 step 4).
**Tests.** Matei's worked example (z ≈ 11.2, stat 1, novelty 0, materiality 1); below the median → stat 0; novelty 1 / 0.5 / 0 cases; seen 90 days ago vs 91 days ago (boundary); disposable ≤ 0 → materiality 1 (no division by zero); MAD = 0 fallback; property: every output in [0, 1].

### E8 · Monte Carlo goal forecast · L 2h · P0 · deps: E1, E6, F2 · suggested: danutu
**Files.** `app/engine/forecast.py`: pure `forecast(inputs, n_paths=10_000, seed) -> Forecast`; shell `forecast_goal(db, user_id, plan_version)` saving `goal_forecasts` with the weekly-snapshot rule.
**Implementation notes.** numpy arrays of shape (paths, months); bootstrap of monthly category totals with context multipliers; lognormal fallback with < 3 months of history; income deterministic or bootstrapped (irregular-income fact); receivables Bernoulli; shocks; the current month = actual + expected rest. **Seed = `blake2b(f"{user_id}|{sim_date}|{plan_version}")`, never Python's `hash()`** (it changes between processes).
**Tests.**
- the same seed in two separate processes (subprocess) → the same probability (catches the `hash()` bug).
- probability ∈ [0, 1]; target ≤ saved → 1.0; target 10× income → ≈ 0.
- property (same seed, common random numbers): +500 income/month → probability ≥ before; adding a receivable → ≥; an emergency pot (no shocks) → ≥.
- p10 ≤ p50 ≤ p90; `expected_reach_date` is `None` when p50 at the deadline is below target.
- an irregular-income persona has a wider p90 − p10 than a salaried one with the same mean.
- zero history → no crash (lognormal path).
- weekly-snapshot flag: the first forecast on/after Monday 00:00 sim time is `true`, once per week.
- performance: 10 000 paths × 7 months < 100 ms (assert < 250 ms so CI isn't flaky).

### E9 · Drivers & options · M 1h · P1 · deps: E8 · suggested: danutu
**Tests.** Drivers exclude essential, household-care and protected categories, are sorted descending and ≥ 0. Options appear only when P < 0.6 or it dropped > 10 pp; at most 3; each is re-simulated and above the current probability; the deadline option only for soft goals; reductions ≤ 25% of the baseline; Matei's protected concerts are **never** in an option; labels come from i18n in both languages.

### E10 · Pots, expected receivables, auto-save, transfers · M 1h · P0 · deps: E2, B3 · suggested: danutu
**Files.** `app/engine/savings.py`: pure `pot_contribution(...)`, `receivables_expected(...)` (`p_repay` 0.9 until `expected_by`, −0.1 per full 14 days after, floor 0), `auto_save_amount(...)` (arch 6.7 cap); shell `auto_save(db, user_id, income_tx_id)` → `transfers(kind=auto_save)` + goal pot `saved` + quiet notification; undo restores both.
**Salary matching.** A credit is a salary when it's within ±20% of an `income_sources` amount and ±3 days of its day of month.
**Tests.**
- pot 3 000 by 15 Aug from 15 Jun (paydays 10 Jul, 10 Aug) → 1 500/payday; deadline passed → 0; saved ≥ target → 0 + pot `completed`.
- `p_repay` at 0, 13, 14, 28 and 140 days overdue (floor 0).
- auto-save: the cap is applied when the balance is low and not applied otherwise; no goal or goal completed → nothing; a credit outside ±20% / ±3 days → not a salary (each boundary tested); undo restores the balance and the pot; undo twice → error.

### E11 · Day-level signals · S 0.75h · P1 · deps: E2, B3 · suggested: danutu
**Files.** `app/pipeline/signals.py`: pure `detect_signals(ctx, ledger_today, plan, prev_forecast, forecast)` → `warning`, `overspend`, `underspend_week`, `category_cap`, `infeasible_plan`, `goal_completed`.
**Thresholds 🟡 (danutu to confirm).** warning: spent > 0.9 × budget; overspend: spent > budget; under (at close): spent < 0.5 × budget; underspend_week: ≥ 20% under; category cap: 80% and 100% of the weekly cap (only the highest level per day is kept).
**Tests.** Every boundary exactly; dedup per (type, date); goal_completed fires once when `goal_pot.saved ≥ goal.amount`.

### E12 · Persona data generator · L 2h · P0 · deps: F2, C1, C2 · suggested: danutu
**Files.** `scripts/generate_personas.py`; `data/personas/<id>/config.json` (inputs) → `profile.json`, `transactions.json`.
**Spec.** `as_of` = 2026-06-15; history 2026-02-15 … 2026-06-14 (4 months); a fixed seed per persona. Streams: recurring (salary on its day, rent, utilities ±10%, subscriptions exact); category streams (Poisson visits × lognormal amounts around the persona's median, with weekday/time preferences); the patterns of arch 16.1 (Matei: Mega Image 3–4×/week on weekdays 12:00–14:00, median 85; a Friday team lunch 60–110 between 12 and 15; Glovo 2×/week in the evening. Ioana: Shop&Go almost daily, median 140, plus Kaufland on Saturdays 300–500. Andrei: two sports streaming subscriptions, football tickets. Bianca: small amounts, weekly tips); calendar (Easter 12 Apr 2026 for Ioana, 1 Iunie for Ioana's kids, 8 Martie for Matei); receipt items on some transactions; the start balance is computed backwards so the end balance equals `profile.current_balance`. Matei's two previous Friday lunches are annotated as answered (supports the 0.7 rule).
**Tests.**
- running the generator twice gives byte-identical files.
- no transaction after 2026-06-14 23:59 Bucharest time.
- Matei: 3–4 weekday-lunch Mega visits in each full week; Mega median 85 ± 8; a lunch every Friday, within 60–110.
- Ioana's Shop&Go median 140 ± 15; her Easter week (6–11 Apr) > 1.5× an average week.
- the salary and rent appear on the right day each month.
- start balance + Σ = `current_balance` exactly (Decimal).
- every `merchant_raw` resolves with C2; every file validates against the F2 models; amounts positive with 2 dp.

### E13 · Calibration of the demo numbers · S 0.75h · P1 (before rehearsal) · deps: E8, E12, B12, C6, A3 · suggested: danutu
**Goal.** Matei on 2026-06-15: **78%** (± 1 pp), after Mega 500 provisional **71%**, after the answer **77%**, last weekly snapshot **72%**. Andrei's TV → inform, Bianca's → ask, Ioana's Shop&Go → auto.
**How.** Tune the generator and profile numbers (savings, income, goal), **never the formulas**.
**Tests.** `tests/acceptance/test_demo_numbers.py` (golden): fails if anyone changes the engine or the data and breaks the demo.

---

## 5. Context layer (C)

### C1 · Fixed lists, labels, formats & data files · M 1h · P0 · deps: F2 · suggested: danutu (David G. reviews)
**Files.** `app/i18n/labels.py` (category / purpose / beneficiary labels RO + EN, `label(enum, lang)`), `app/i18n/format.py` (`format_money`, `format_pct`, `format_date`, RO and EN), `data/merchants.json` (~40 Romanian merchants with canonical name, aliases, category, MCC, typical basket, `multi_category`: Mega Image, Shop&Go, Lidl, Kaufland, Carrefour (multi), Profi, Penny, Auchan (multi), eMAG (multi), Altex (multi), Flanco (multi), Decathlon, Glovo, Tazz, Bolt, Uber, Petrom, OMV, MOL, Rompetrol, Dr.Max, Catena, Sensiblu, Help Net, Libris, Cărturești, Diverta (multi), Steam, Netflix, Spotify, Digi, Orange, Vodafone, Enel, Engie, E.ON, CFR Călători, Wizz Air, Ryanair, Booking, a few restaurants, sports streaming services), `data/priors.json` (single-adult monthly medians + basket medians + CV per category + city index; numbers agreed with E6), `data/products.json` (3 mock products, arch 16.5), `data/calendar.json` (fixed-date events + configurable ones like school start and Black Friday).
**Tests.** Every file validates against a schema; every merchant category is a valid `Category`; aliases are unique across merchants (case- and diacritics-insensitive); every enum value has an RO and an EN label; `format_money(10000, "ro") == "10.000 lei"`, `(30.4, "ro") → "30,40 lei"`, `(1234.5, "en") → "1,234.50 lei"`; priors positive; products have `min_months < max_months` and `mock: true`.

### C2 · Merchant normalisation · S 0.5h · P0 · deps: C1 · suggested: danutu
**Files.** `app/context/normalize.py`: pure `normalize(merchant_raw, mcc, script_category) -> (merchant_id | None, name, category)`. Fold case and diacritics; strip store numbers, city names and payment prefixes (`POS`, `PAYU*`, `SC`, `SRL`); longest alias match; MCC fallback table (5411 groceries, 5812/5814 restaurants, 5541 fuel, 5912 pharmacy, 4111 transport, 4511 travel, 5732 electronics, 5941 sport, 5942 books, 5815–5817 subscriptions/entertainment, 4814 telecom, 4900 utilities); a script category always wins.
**Tests.** `"MEGA IMAGE 0451 BUCURESTI"` → Mega Image / groceries; `"SHOP&GO 123"` → Shop&Go; `"PAYU*EMAG.RO"` → eMAG, multi; `"GLOVO*ORDER 8812"` → food_delivery; `"Cărturești Verona"` with and without diacritics; lowercase input; unknown + MCC 5411 → groceries with no merchant; unknown with no MCC → `other`; empty string → `other`; idempotent on canonical names; property: never raises on arbitrary Unicode (hypothesis).

### C4 · Signature library & `signatures_for_fact` · L 1.5h · P0 · deps: F2, C1 · suggested: David G.
**Files.** `data/signature_library.json` (~40 entries: occupations with synonyms (sports analyst, developer, designer, photographer, driver, teacher, student), kids by age band (expects_event: school supplies Aug–Sep for 6–18, 1 Iunie for under 14; explains: kids' clothing/toys), pets, vehicle (fuel, RCA yearly, ITP, parking), activities (running shoes with a 180–300-day cycle, gym, cycling, gaming, photography, festivals, football), trips (travel in the window → planned_event), priorities (`protects`)), `app/context/library.py`.
**Logic.** Library lookup by fact type + normalised value (synonyms, contains-match); Claude's signatures validated with F2, strength capped at 0.9, unknown fields dropped, **health/pharmacy `explains` signatures from Claude are dropped** (sensitive); merge: library wins on the same (effect, category); `origin` set.
**Note.** The household **multiplier** is computed by E6 from the facts; household library entries carry only `expects_event` / `explains` (no duplicated scaling).
**Tests.** Every library entry validates; each persona fact yields the expected signatures (Andrei: electronics TV + streaming as `work_tool`); synonyms and case ("Analist Sportiv", "analist sportiv la o televiziune"); an LLM-only fact ("fac cosplay") keeps valid signatures with origin `llm`, strength ≤ 0.9; an invalid purpose, `amount_min > max` or a health signature is dropped and logged; a library + LLM duplicate keeps the library one; empty input → `[]`; a `priority: protected` fact → a `protects` signature.

### C5 · `life_fit` & the explanation · L 1.5h · P0 · deps: C4, F2 · suggested: David G.
**Files.** `app/context/life_fit.py`: pure `life_fit(tx, ctx) -> FitResult(score, source, fact_id, rule_id, explanation_key, params)`, arch 5.3.4 step 3. Saturation: "similar" = same category and (an item keyword match or an amount within ±30%). Precedent: a user-answered transaction at the same merchant, or same category with amount ±30% → `0.8 × (1 − |Δ| / amount)`. `expects_event`: date/months window + category + amount within ±50% of expected. Tie-break: higher score → confirmed over hypothesis → most recent fact. Explanations come from i18n templates (RO + EN).
**Tests.**
- Andrei's TV with items → 0.855 ± 0.005; without items → 0.684 (still ≥ 0.6); Bianca → 0 (no source).
- saturation: a previous TV 60 days ago with a 900-day cycle → factor 0.0667; 900+ days → 1.
- a hypothesis fact (confidence 0.5) caps the score; amount 2× above the range → amount term 0; 1.5× → 0.5.
- weekday mismatch → time term 0; item keywords match case- and diacritics-insensitively ("Televizor 65\"").
- precedent → 0.8 × similarity; Ioana's school supplies in August match `expects_event`.
- the explanation exists in RO and EN and mentions the fact.
- property: score ∈ [0, 1]; deterministic.

### C6 · `evaluate_transaction` · M 1h · P0 · deps: C2, C5, E6, E7 (C8 rule match stub) · suggested: David G.
**Files.** `app/context/evaluate.py` (pure `evaluate(ctx, tx) -> Evaluation`), `app/context/service.py` (the §15 shell). Arch 5.3.4 steps 1–7, including recurring-bill detection (a fixed-cost match within ±10% amount and ±3 days, or a monthly recurrence in history for utilities/telecom/housing), `question_hint` (reason key + params, e.g. ratio "~6×", and `ask_what_item`), `goal_impact = amount / max(remaining_to_goal, 1)`.
**Tests.**
- acceptance cases #1, #3–#7, #10, #11 of arch 16.3.
- each hard filter at its boundary: 49.99 vs 50.00; with a 7 000 income the floor is 70 → 69.99 ignored, 70.00 evaluated; rent 2 200 (+10% exactly) → auto, 2 201 → evaluated.
- credit → auto; pharmacy 5 000 → auto, never ask; a flight with an active trip pot → `planned_event` + `pot_id`; a classify rule at 0.9 → auto with its label; at 0.7 → partial life-fit, no ask.
- thresholds: unexplained exactly 0.55 → ask; 0.5499 → auto; inform needs raw ≥ 0.5 **and** life_fit ≥ 0.6.
- `ask_what_item` only for multi-category merchants without items.
- for `ask`: provisional `effective_amount = amount`, purpose `unknown`; an explanation exists for auto/inform, in the user's language.
- performance: 1 000 evaluations < 1 s.

### C7 · Question policy · M 1h · P0 · deps: C6, B3 · suggested: danutu (David G. reviews)
**Files.** `app/context/questions.py`: pure `pick_question(candidates, ctx, now, sim_mode)`, `budget_state(ctx, today)`, `default_reading(tx)`.
**Tests.**
- #12: two candidates → the higher priority is asked, the other `ask_later`.
- today's question already used by an overspend question → `None`.
- quiet hours: 22:00 and 07:59 quiet, 08:00 allowed; off in `sim_mode`.
- weekly soft cap: the 5th candidate of the week → `None`.
- back-off: 2 consecutive ignored → 1 question every 2 days for 7 days.
- a matching `suppress` rule → never asked; volunteered context doesn't count.
- `ask_later` expires after 48 h with the default reading; deterministic tie-break (older transaction first); a candidate whose transaction is already answered is skipped.

### C8 · Learning rules · M 1h · P1 (the seeded explicit rule is P0 for Scene D) · deps: F2, B3 · suggested: David G.
**Files.** `app/context/rules.py`: pure `learn(annotated_tx, history, rules) -> RuleChange | None`, `rule_matches(rule, tx)`, `decay(rules, today)`.
**Tests.** Two similar explanations (same category and weekday, time ±1 h, amount ±40%) → a new rule at 0.7; the third → 0.9; a different weekday → none; amount +41% → none; an explicit recurrence through the tool → 0.9 at once; amount > 2× the max → no match; time-window bounds inclusive; decay after 60 days without a hit → −0.2, below 0.5 → inactive; a correction → misses + 1, two misses → inactive; a `suppress` rule matches without classifying; acceptance #9.

### C9 · Propagation on a fact change · M 1h · P1 · deps: C4, C6, E6, E3, E4, E8 · suggested: David G.
**Files.** `app/context/propagate.py` shell `on_fact_changed(db, user_id, fact_id)`: replace signatures → household scale + baselines → re-evaluate the last 30 days **only where `annotation_source ∈ {auto, fact, default}`** (an `answer` or `user_edit` is never overridden) → save the changed annotations (+ ledger deltas via E3) → recompute plan (reason "fact: …") → forecast → push events.
**Tests.** Andrei's TV was asked yesterday (source auto) → add the occupation → the TV becomes `work_tool` (inform) with the explanation updated, ledger unchanged; the same TV after a user answer → unchanged; Ioana's temporary mother → scale 2.6 in July only (#13); deleting a fact removes its signatures and re-evaluates; plan version + 1 with the reason; running twice → no further changes; 30 days < 200 ms.

### C10 · Hypotheses inference · S 0.75h · P2 · deps: C4, B3 · suggested: David G.
**Tests.** Fuel at Petrom/OMV in ≥ 3 of 4 weeks → a vehicle hypothesis at 0.5; a monthly pet shop for 3 months → pet; monthly kindergarten → child; Decathlon + race fee → runner; a changed rent amount → "moved?"; weekly pharmacy → **no** health hypothesis; an existing confirmed fact → no duplicate; a rejected one → never again; at most 1 new hypothesis per run.

### C11 · Calendar expected events · S 0.5h · P2 · deps: C4, C1 · suggested: David G.
**Tests.** Orthodox Easter computed with the Meeus Julian algorithm: 2024 → 5 May, 2025 → 20 Apr, 2026 → 12 Apr. Fixed dates (Crăciun, 1 Iunie, 8 Martie) come from `calendar.json`, and the configurable ones are read from it. Events are produced only for relevant facts (1 Iunie and school only with kids).

### C12 · Product ranking ("compare products using customer context") · S 0.5h · P2 · deps: C1 · suggested: David G.
**Tests.** Horizon < 3 months → the flexible pot first; 3–12 months → savings account; ≥ 6 months with a fixed amount and stable income → term deposit first; irregular income → liquidity first; every reason in RO and EN; every product marked mock.

---

## 6. Agent & LLM (A)

### A1 · Claude client wrapper + `FakeLLM` · S 0.5h · P0 · deps: F1 · suggested: David G.
**Files.** `app/agent/llm.py` (`LLM.create(system, messages, tools)` building the arch 6.8 parameters: model from env, `max_tokens=8000`, `output_config={"effort": …}`, **no** temperature, `tool_choice` left as auto, the optional refusal-fallback beta behind a setting, timeout 30 s, `max_retries=2`; maps SDK errors to `LLMUnavailable` / `LLMBadRequest`), `tests/fakes/fake_llm.py` (`FakeLLM(script)` returns scripted responses in order and records every request).
**Tests.** The exact kwargs sent (no `temperature`, effort as configured, model from env, max_tokens 8000); fallback setting on → beta header + `fallbacks: "default"`; FakeLLM order and "script exhausted" error; `RateLimitError` / `APIConnectionError` / 5xx → `LLMUnavailable`; 400 → `LLMBadRequest` (not retried, logged). Live (`-m live`): one tiny real request returns `end_turn`.

### A2 · Tool schemas, registry & `tools_for` · M 1h · P0 · deps: F2 · suggested: David G.
**Files.** `app/agent/tools.py`: one Pydantic input model per tool of arch 6.6; JSON schema with `strict: true`, `additionalProperties: false`, `required`; descriptions that say **when** to use the tool; `REGISTRY: name → (InputModel, handler, flags{money, write, read_only})`; `tools_for(state, trigger)`.
**Tests.**
- every schema is valid JSON Schema (jsonschema), with `additionalProperties: false` at every object level.
- names are unique snake_case ≤ 64 chars; every description is ≥ 40 chars and says when to use it.
- **no `user_id` property anywhere** (recursive scan).
- `tools_for` matrix: no active goal → `set_goal` and not `update_goal`; active goal → the reverse; proactive → exactly the read-only set of arch D22.
- deterministic order (cache-friendly); every entry has a handler; the `money` flag set equals the MONEY_TOOLS list of arch 6.7 (golden).
- live (`-m live`): one request with the full tool list is accepted by the API (proves the strict schemas are valid).

### A3 · Tool executor & handlers · L 2h · P0 · deps: A2, B3, E3, E4, E8, E10, C4, C8, C9 (stubs ok) · suggested: David G.
**Files.** `app/agent/executor.py` (arch 6.4 rules + D18 recompute + defence in depth: a write tool in a proactive run → `not_allowed_in_proactive`), `app/agent/handlers/*.py` (transactions, receivables, facts, rules, pots, goals, income/costs, events, shaping, reads, ui).
**Key logic.** `annotate_transaction`: the transaction belongs to the user; the effective amount = `own_amount` if given (it wins over `people_count`), else `split_share(amount, people_count)`, else the baseline estimate (`estimated: true`, clamped ≤ amount); a receivable when `others_will_repay` and the others' share > 0; E3 `on_annotation_changed`; C8 `learn`; mark the open question answered. `offer_payment_request`: the receivable must be open; adds an action card; status unchanged. `add_life_fact`: validate the value; C4 signatures; C9 propagation. `create_pot`: E10 contribution.
**Tests (db).**
- each tool: happy result shape; invalid input → `is_error` with a message Claude can act on; another user's ids → `not_found`.
- every money tool's result contains `plan` and `forecast` with the previous values.
- annotate maths: 5 people → 100 + receivable 400 (amount_each 100); `own_amount` 120 → 120 + 380; `own_amount > amount` → error; `people_count = 1` → no receivable; both given → `own_amount` wins; neither → estimated, ≤ amount.
- correcting an annotation ("doar pentru mine") → the receivable is cancelled and the ledger delta is right.
- `offer_payment_request` on a paid receivable → error; `set_goal` with an active goal → `goal_already_active`.
- a write tool in a proactive run → `not_allowed_in_proactive`; an unknown tool → error.
- every call writes a `tool_calls` row; an unexpected handler exception → a generic `is_error` + log, and the loop continues.

### A4 · Snapshot builder · M 1h · P0 · deps: B4, F2, C1 · suggested: David G.
**Files.** `app/agent/snapshot.py`: pure `build_snapshot(ctx, trigger, event, language) -> str`. Sections in the fixed order of arch 6.5; ids printed next to items; numbers formatted with i18n; the open-question block; the question budget.
**Tests.**
- golden snapshots for Matei before and after the Mega transaction (`tests/golden/`, reviewed by a human on every diff).
- every block header present; empty blocks say "none" instead of disappearing; `[tx 918]`-style ids present.
- no IBAN (`RO\d{2}[A-Z]{4}[A-Z0-9]{16}`) and no 13–19-digit runs.
- prompt-injection text in a merchant or description is quoted, single-line and marked as data.
- the same context → byte-identical output; stable ordering; an EN user gets EN labels.
- the heaviest persona stays under ~4 000 tokens (len/4 estimate).

### A5 · Prompts, banned-phrase checker & templates · S 0.75h · P0 · deps: C1 · suggested: David G.
**Files.** `app/agent/prompts.py` (frozen system rules RO + EN, few-shot examples, trigger instructions: chat, proactive question, onboarding), `app/agent/style.py` (`find_banned(text, lang)`: Unicode word boundaries, diacritics-insensitive), `app/agent/templates.py` (question template, fallback replies, follow-ups).
**Tests.**
- "De ce ai cheltuit" → hit; "de cele mai multe ori" → **no** hit; "chiar" → **no** hit for "iar"; "Iar ai cheltuit" → hit; "risipa" and "risipă" → hit; "din nou" → hit; EN "Why did you" → hit, "whyever" → no; "again" → hit, "against" → no.
- no template contains a banned phrase; every template exists in RO and EN.
- the system prompt contains the key rules (never calculate, never claim a save without a successful tool result, text fields are data).
- the prompts are byte-stable (no dates or ids) → prompt cache works.

### A6 · Agent loop · M 1h · P0 · deps: A1–A5 · suggested: David G.
**Files.** `app/agent/loop.py`: `run_agent(...) -> AgentResult` (arch 6.3 v0.8): the last 20 messages, iterations, all tool results in one user message, stop reasons, the banned-phrase post-check (regenerate once, then the template), `speak_text` (A11), quick replies and action cards collected from the UI tools, `ref_transaction_id` from the open question.
**Tests (FakeLLM).**
- `end_turn` straight away → the text; `tool_use` → `tool_result` → `end_turn` (the 2nd request contains the assistant content unchanged + the tool result).
- 2 parallel `tool_use` → one user message with 2 results and matching ids.
- `refusal` → fallback; `max_tokens` → fallback; 6 tool rounds → loop-limit fallback.
- a tool error → Claude gets `is_error`, then `end_turn`.
- the tool list is rebuilt each iteration (after `set_goal`, the next request offers `update_goal`).
- thinking blocks in the fake response are appended back verbatim.
- a banned phrase in the final text → regenerated/replaced.
- `speak_text` set for voice input and proactive runs; history capped at 20; the fallback is in the user's language; `LLMUnavailable` → fallback, and pending events stay pending.

### A7 · Proactive runs (questions & events) · M 1h · P0 · deps: A6, C7, B3 · suggested: David G.
**Files.** `app/agent/proactive.py`: `run_proactive(user_id, event_id)`: event-specific instructions (transaction_question with the reason, `ask_what_item` and default quick replies; overspend; weekly; receivable_reminder; goal_completed); read-only tools; template fallback after 5 s; saves the message with `speak = true` + refs; marks the event asked; a notification for question types.
**Tests.**
- a transaction question → a message with ≥ 3 quick replies, `speak_text`, `ref_transaction_id`; event `asked`; notification created.
- LLM timeout → the template "Am văzut 500 lei la Mega Image…" (RO) and the EN version for an EN user; `ask_what_item` → "Ce ți-ai luat de la eMAG?".
- the fake tries `annotate_transaction` → error result (read-only).
- a question longer than 18 words is logged as a warning (not a failure).
- the same event twice → no duplicate message; a `goal_completed` event doesn't use the question budget.

### A8 · Live onboarding · S 0.5h · P2 · deps: A6, A3 · suggested: David G.
**Tests.** `complete_onboarding` without a life fact → an error listing `life_context`; with everything → `onboarded_at` set + first plan + forecast; a scripted rich message through FakeLLM → the expected tool calls in order; onboarding rows in the eval set.

### A9 · Deterministic fallbacks (demo safety) · S 0.75h · P1 · deps: A3, A5 · suggested: David G.
**Files.** `app/agent/fallbacks.py`: known quick-reply labels → deterministic actions when the LLM is down ("Doar pentru mine" → self/unplanned; "Și pentru alții" → card "Câți ați fost?" [2] [3] [4] [5] [6+]; "5" → `annotate(people_count=5, others_will_repay=true)`; "Ceva plănuit" → link to a matching pot, or ask which; "Prefer să nu spun" → unknown + suppress similar).
**Tests.** Scene A with the LLM down, via the chips → the same final state as the LLM path (100 + 400); unknown free text with the LLM down → a polite "can't process now" reply and **nothing changed**; the EN labels map too.

### A10 · LLM eval set & runner · M 1h · P1 · deps: A6, A3, D1 · suggested: David G.
**Files.** `tests/eval/answers.jsonl` (60–100 rows: persona, open question, utterance, expected tool calls + key args), `tests/eval/run_eval.py` (live; prints an accuracy table; writes `tests/eval/reports/<timestamp>.md`).
> **Status (2026-10-29):** `answers.jsonl` and `run_eval.py` weren't written; the live evals are `tests/eval/test_llm_live.py`, `test_tools_live.py` and `test_onboarding_live.py` (marker `live`).
**Tests.** The runner's scoring is unit-tested with FakeLLM (tool name match, key-arg match with tolerance, multi-intent order-insensitive); the dataset validates (persona exists, tools exist). **Targets:** ≥ 90% overall, 100% on the demo rows. It costs real money, so run it only after prompt changes.

### A11 · Language detection & `speak_text` · S 0.5h · P1 · deps: A5 · suggested: David G.
**Files.** `app/agent/language.py`: `detect_language(text, current)` (diacritics + RO/EN stopwords; short or ambiguous text keeps the current language), `make_speak_text(text, lang)` (no emoji or markdown, ≤ 2 sentences, "77%" → "77 la sută" / "77 percent").
**Tests.** "Am luat si pt colegi" → ro; "I bought it for my colleagues" → en; "ok" / "5" → current; "am dat split cu colegii" → ro; `speak_text` removes emoji and asterisks, keeps ≤ 2 sentences and converts percentages per language.

---

## 7. Data, demo & quality (D)

### D1 · Persona life facts & seeded rules · S 0.75h · P0 · deps: F2, C4 · suggested: David G.
**Files.** `data/personas/<id>/facts.json` (Matei, Andrei, Bianca, Ioana; Alex empty), Matei's seeded Friday rule (0.7, 2 hits).
**Tests.** Every file validates; `signatures_for_fact` gives the expected signatures per persona; Ioana → scale 2.1 via E6; no sensitive facts anywhere.

### D2 · Scenario files · S 0.5h · P0 · deps: E12, C1 · suggested: danutu
**Files.** `data/scenarios/{matei_mega_500, andrei_tv, bianca_tv, bianca_tv_noitems, matei_flight, matei_friday_lunch, ioana_shopgo_350, matei_shopgo_350}.json` (persona, merchant_raw, mcc, amount, items, time relative to the sim date).
**Tests.** Each validates; the persona exists; the merchant normalises; evaluating it on its seeded persona gives the arch 16.3 decision.

### D3 · Acceptance suite (arch 16.3) · M 1h · P1 (cases #1–#7 are P0) · deps: C6, A3, E8, B12 · suggested: David G. (+ danutu for the engine cases)
**Files.** `tests/acceptance/test_context_acceptance.py`: the 15 cases on the seeded DB, through services + pipeline, with FakeLLM scripting the tool calls for the answers (deterministic).
> **Status (2026-10-29):** `test_context_acceptance.py` wasn't written; the cases are covered by `tests/unit/context/` and `tests/unit/agent/test_scene_a.py`, the demo numbers by `tests/acceptance/test_demo_numbers.py`.

### D4 · Demo client · S 0.75h · P0 · deps: B5, B7, B9, B10 · suggested: bomboe (David G. writes the scene scripts)
**Files.** `scripts/demo_client.py` (httpx + websockets): logs in as a persona through `savings-dev`, resets, runs a scene, prints every WS event with its timing and **asserts the expected end state**; `--scene A --answer "Am luat și pentru colegi, suntem cinci"`; `--llm-off` uses the chip path.
> **Status (2026-10-29):** `demo_client.py` wasn't written; `scripts/smoke_local.sh` brings the stack up and fires Scene A's transaction.
**Tests.** It's the end-to-end test: Scene A asserts effective 100, receivable 400, probability 77 ± 1; run locally and against the hosted server.

### D5 · Demo runbook & rehearsal · S 0.5h · P1 · deps: D4 · suggested: everyone
**Files.** `backend/docs/demo-runbook.md`: before the demo (reset, warm-up LLM call, WS check), timing per scene, fallback steps, who clicks what, the backup video.

### D6 · Security & privacy review · S 0.5h · P1 · deps: most tasks · suggested: David G. (review), bomboe (fixes)
**Checklist.** Isolation tests exist for every resource; internal and sim gating; no secrets in the repo (`git grep -n "sk-ant"`); prompt injection; data minimisation; logs. **Output:** `backend/docs/reviews/security.md`.

---

## 8. The checkpoint and what to cut

**Checkpoint (hour 11–12 in arch §13):** `scripts/demo_client.py --scene A` passes against the local stack, LLM on and LLM off.
**P0 set:** F1–F3, B1–B5, B6a, B6b (request-payment only), B7–B10, B12, B14, E1–E4, E6–E8, E10, E12, C1, C2, C4–C7, A1–A7, D1, D2, D4.
**Cut order if behind** (arch §13): B11 weekly/preemptive jobs → C10 → C11 → C12 → E9 options → C8 beyond the seeded rule → pots (Scene C) → A8. **Never cut:** Scene A, Scene B, the seeded personas, the chip fallback, plan adaptation, the tests of the P0 set.
