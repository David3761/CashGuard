# Bomboe: API tasks (backend platform)

> Assigned 2026-10-28 by David G. **Scope:** the platform half of `api/`: DB, services, auth, REST, WebSocket, the pipeline plumbing, chat orchestration, simulator, jobs/cron, seed loader, notifications, hosting, audit logging, and the test fixtures (F3).
> **Not yours:** the money maths (`app/engine/`, danutu) and the context layer + agent (`app/context/`, `app/agent/`, David G.). You *call* their functions through the contracts in arch §15; you never re-implement them.
>
> **Read first:** [`api/docs/how-we-work.md`](api/docs/how-we-work.md) (the step loop and templates), [`api/docs/work-breakdown.md`](api/docs/work-breakdown.md) §0 (conventions + the test checklist), and the architecture doc [`api/docs/savings-coach-backend-architecture.md`](api/docs/savings-coach-backend-architecture.md) §4, §5.1, §5.2, §8, §9, §10, §11, §15.
>
> **Opening prompt for Claude Code:**
> *Read `api/docs/how-we-work.md`, `api/docs/work-breakdown.md` §0, the architecture doc sections listed in `Bomboe.md`, and `Bomboe.md`. We're doing task <ID>, step <n>. Follow the loop: plan → test analysis over every category → tests first (red) → implement (green) → `make check` → self-review → step report. Then stop and wait for my review.*

---

## 0. Overview

| Order | ID | Task | P | h | Status |
|---|---|---|---|---|---|
| 1 | B1 | docker-compose, env, Keycloak realm, cron container | P0 | 0.75 | ✅ steps 1–3 (step 4 after B6a/B8) |
| 2 | B2 | DB models for every table | P0 | 1.5 | ✅ (+ Alembic, `goals.soft`) |
| 3 | F3 | Test fixtures (DB, API, auth, WS) | P0 | 1 | ✅ (`seeded_db` after B12) |
| 4 | B3 | CRUD services | P0 | 1.5 | ✅ |
| 5 | B4 | `load_user_context` read model | P0 | 0.75 | ◐ stub (Matei) done |
| 6 | B5 | Auth (JWT/JWKS, `current_user`, internal role, WS token) | P0 | 1 | ◐ step 1 done |
| 7 | B7 | WebSocket manager + events + push-after-commit | P0 | 0.75 | ☐ |
| 8 | B8 | Ingestion + processing pipeline | P0 | 1.5 | ☐ |
| 9 | B9 | `POST /chat` + background agent run | P0 | 0.75 | ☐ |
| 10 | B6a | REST core endpoints | P0 | 1 | ☐ |
| 11 | B12 | Seed loader | P0 | 0.75 | ☐ |
| 12 | B10 | Simulator | P0 | 1 | ☐ |
| 13 | B6b (step 1) | `POST /receivables/{id}/request-payment` (+ list) | P0 | 0.5 | ☐ |
| 14 | B14 | Hosting & deploy | P0 | 1 | ☐ |
| 15 | B6b (rest) | /forecast, /pots, /life-facts, /products, /life-profile | P1 | 0.5 | ☐ |
| 16 | B11 | Day jobs + internal endpoints + cron | P1 | 1 | ☐ |
| 17 | B13 | Notifications service + RO/EN templates | P1 | 0.5 | ☐ |
| 18 | B15 | Audit logging + privacy | P1 | 0.5 | ☐ |

**Load:** P0 ≈ 13.75 h · total ≈ 16.25 h. "H+n" below means *n hours after we all start building*.

---

## 1. What others need from you, and when

| Deliverable | Who needs it | Needed by | Task |
|---|---|---|---|
| The DB schema (`create_all` works) | everyone's db tests | H+3 | B2 |
| Test fixtures `db`, `db_committed`, `client`, `as_user`, `make_token`, `ws_connect` | everyone | H+3.5 | F3 |
| **Stubs** of the services in arch 15.1 (right signatures, simple bodies) + `load_user_context` returning a builder-made Matei | David G. (shells, snapshot), danutu (shells) | **H+2** | B3/B4 |
| Real services + `load_user_context` | David G., danutu | H+5 | B3, B4 |
| `ws.push_after_commit` + the event builders | David G. (tool handlers push events) | H+5 | B7 |
| The pipeline calling `evaluate → apply → recompute → forecast → pick_question → proactive` | the checkpoint | H+7 | B8 |
| `/chat` calling `run_agent` | the checkpoint | H+7 | B9 |
| `/sim/transaction`, `/sim/reset` | David G.'s demo client (D4) | H+7.5 | B10 |
| Seeded DB | David G.'s acceptance tests (D3), danutu's calibration (E13) | H+7.5 | B12 |

## 2. What you need from others, and when

| From | What | For | Until it arrives |
|---|---|---|---|
| David G. | F1 repo skeleton | everything | do B1 (compose + realm don't need it) |
| David G. | F2 step 1: enums + money (H+1); F2 steps 2–3: models + results (H+1.5) | B2 CHECK constraints, B3 return types | write the tables first, add CHECKs when enums land |
| danutu | stubs: `apply_transaction`, `on_annotation_changed`, `recompute_plan`, `forecast_goal`, `auto_save`, `recompute_baselines` (H+2) | B8, B6a, B12 | your own temporary no-op |
| David G. | stubs: `evaluate_transaction`, `pick_question`, `default_reading`, `run_agent`, `run_proactive`, `signatures_for_fact`, `on_fact_changed` (H+2) | B8, B9, B11, B12, B6b | your own temporary no-op |
| David G. | C1: `merchants.json`, `products.json` (H+2.5); D1 persona facts (H+4); D2 scenarios (H+6); A5 banned-phrase checker; C1 `app/i18n/format.py` | B12, B10, B13 | seed only what exists |
| danutu | E12 persona data files `profile.json`, `transactions.json` (H+5.5) | B12 | seed one hand-written persona |

---

## 3. Tasks

### B1 · docker-compose, env & Keycloak realm · P0 · 0.75 h · deps: —
**Goal.** One command brings up Postgres (dev + test), Keycloak with our realm, the API and cron.
**Files.** `api/docker-compose.yml`, `api/Dockerfile`, `api/keycloak/realm-cashguard.json`, `api/cron/crontab`, `api/cron/run.sh`, `api/scripts/smoke_local.sh`, `api/.env.example` (add the Keycloak/cron vars).

- **Step 1: compose skeleton.** Services `db` (postgres:16, volume), `db-test` (postgres:16, port 5433, `tmpfs` for speed), `api` (built from `Dockerfile`, uvicorn `--workers 1`, depends on db). *Tests:* `docker compose config` is valid; `db-test` accepts a connection (`pg_isready`).
- **Step 2: Keycloak realm.** `keycloak` service (pinned version) with `--import-realm`. Realm `cashguard`: client `savings-frontend` (public, standard flow + PKCE S256, redirect URIs `ro.cashguard.app:/oauthredirect` and `http://localhost:*`); `savings-cron` (confidential, service account, realm role `internal`); `savings-dev` (direct access grants, dev/test only); users `matei`, `andrei`, `bianca`, `ioana`, `alex` with **fixed ids** (these become `users.keycloak_sub` in the seed) and known dev passwords; access token lifespan 1800 s. *Tests (unit, `tests/unit/test_realm.py`):* the JSON parses; exactly these 3 clients with these flags; PKCE method S256 on `savings-frontend`; redirect URIs present; 5 users with the expected ids; lifespan ≥ 1800; `savings-cron`'s service account has role `internal`; `savings-dev` isn't public-facing in prod docs (note).
- **Step 3: cron container.** `cron/run.sh <endpoint>`: get a client-credentials token from Keycloak, then `curl -fsS -X POST -H "Authorization: Bearer …" $API/internal/<endpoint>`; `crontab` as arch §10. *Tests:* `shellcheck` clean; a dry-run flag prints the URL without calling.
- **Step 4: smoke script.** `scripts/smoke_local.sh`: compose up → wait for health → password-grant token for `matei` via `savings-dev` → `GET /api/me` 200 → cron token → `POST /api/internal/process` 2xx. *Test:* run it; paste the output in the step report.

**Done when.** `docker compose up -d` + `scripts/smoke_local.sh` pass on a clean machine.

### B2 · Database models (every table) · P0 · 1.5 h · deps: F1, F2
**Goal.** The schema exactly as arch §4 (4.1, 4.2 incl. `transfers.kind/pot_id/income_transaction_id`, 4.4 incl. the column additions).
**Files.** `app/db/models.py` (SQLAlchemy 2, typed `Mapped[]`), `app/db/session.py` (async engine, `async_sessionmaker`, `get_db` dependency, `unit_of_work()` context manager), `app/db/init.py` (`create_all`, `drop_all`).
**Conventions.** Money `NUMERIC(12,2)`; JSON `JSONB`; times `timestamptz`; enums as `String` + `CHECK (col IN (…))` generated from the F2 enums (one helper `enum_check(col, Enum)`), so adding a value is a one-line change.

- **Step 1: core tables.** `users` (+ `keycloak_sub` UNIQUE, `language`, `coach_style`, `household_scale`, `onboarded_at`, `timezone`, `city`), `accounts`, `goals` (+ partial unique index active goal per user), `income_sources`, `fixed_costs`, `life_events` (+ `status`), `life_profile`, `plan_preferences`, `products` (+ new columns), `sim_clock`. *Tests (db):* `create_all` then `drop_all` succeed; an invalid `language` → `IntegrityError`; a second active goal → error; completed + active → ok.
- **Step 2: money flow tables.** `transactions` (all v0.8 columns; CHECK `amount > 0`, CHECK `0 ≤ effective_amount ≤ amount`; indexes `(user_id, status)`, `(user_id, occurred_at)`), `day_ledger` (PK `(user_id, date)`), `plans` (UNIQUE `(user_id, version)`, `reason`, `trigger_ref`), `slips`, `reflections`, `transfers`. *Tests:* each CHECK (negative amount, effective > amount, unknown purpose); duplicate plan version → error; duplicate ledger day → error; `Decimal("0.30")` round-trips exactly.
- **Step 3: conversation tables.** `agent_events` (v0.8 columns + stored `event_date`; partial unique `(user_id, type, event_date)` for day-level types and `(user_id, type, ref_transaction_id)` for transaction types; index `(user_id, status)`), `messages` (v0.8 columns; index `(user_id, created_at)`), `notifications` (+ `agent_event_id`, `message_id`), `agent_runs`, `tool_calls`. *Tests:* two `overspend` on the same date → error; two `transaction_question` for different transactions on the same date → ok; the same transaction twice → error; JSONB with `ă î ș ț` + emoji round-trips; `timestamptz` keeps the instant.
- **Step 4: life-context tables.** `life_facts`, `spending_signatures`, `pattern_rules`, `receivables`, `pots`, `goal_forecasts`, `category_baselines` (PK `(user_id, category)`), `merchants`. *Tests:* CHECKs on every enum column; **golden schema test**: the set of `(table, column)` equals a list copied from arch §4 (a missing or misspelt column fails); deleting a user removes all its rows (needed by `/sim/reset`), or the explicit delete order is tested.

**Done when.** The golden schema test passes and `make check` is green.

### F3 · Test fixtures (DB, API, auth, WS) · P0 · 1 h · deps: F1, B1, B2
**Goal.** Writing a db/api/ws test takes one fixture. Everyone depends on this.
**Files.** `tests/conftest.py`, `tests/fixtures/db.py`, `api.py`, `auth.py`, `ws.py`, `tests/README.md`.

- **Step 1: DB fixtures.** Session-scoped async engine on `TEST_DATABASE_URL` (the `db-test` service); `drop_all` + `create_all` once per session. `db`: a function-scoped session inside an outer transaction with a nested SAVEPOINT, rolled back after the test (the SQLAlchemy 2 "join an external transaction" recipe, async). `db_committed`: real commits, then `TRUNCATE … RESTART IDENTITY CASCADE`. `seeded_db` (added after B12): seed once into a template database and clone it per module. *Tests:* a row written in test A is not visible in test B; `db_committed` leaves every table empty; nested transactions inside a test still roll back.
- **Step 2: auth, API, WS fixtures.** `auth`: an RSA keypair per session; `make_token(sub, roles=(), exp_in=300, iss=settings.KEYCLOAK_ISSUER, azp="savings-frontend", alg="RS256", kid="test")`; override the app's JWKS fetcher to return the test public key. `client`: `httpx.AsyncClient(transport=ASGITransport(app), base_url="http://test/api")`; `as_user(user)` adds `Authorization: Bearer`. `ws_connect(user)`: Starlette `TestClient` WebSocket helper. *Tests:* a `make_token` token passes `verify_token`; `exp_in=-1` fails with `token_expired`; `as_user` reaches `/me`.
- **Step 3: README.** One example per fixture; how to run each marker.

**Done when.** Merged and announced to danutu and David G.

### B3 · CRUD services · P0 · 1.5 h · deps: B2
**Goal.** Every read and write the others need, scoped by `user_id`, returning F2 domain objects.
**Files.** `app/services/<group>.py`.
**Rules.** Every function takes `db` and `user_id` and filters by it (except `products`, `merchants`). Reading or writing another user's row → `DomainError("not_found", status=404)`. Reads return F2 domain objects (`TxView`, `LifeFact`, …), not ORM rows. State transitions are validated (`invalid_transition`, 409).

> **First (H+2): commit stubs** with the exact signatures of arch 15.1 (bodies: `raise NotImplementedError` or a simple version) so the others can code against them.

- **Step 1: profile & plan inputs.** `users` (get by id / by keycloak_sub, update language / coach_style / household_scale, set onboarded), `accounts` (get, adjust balance), `goals` (create, update, complete, get_active), `income_sources`, `fixed_costs`, `life_events` (create, update, cancel, list_planned), `plan_preferences` (get, update), `products` (list), `merchants` (list, get). *Tests:* create → get → list → update → delete for each; **isolation** for each (user B → `not_found`); a cancelled event leaves `list_planned`.
- **Step 2: money flow.** `transactions`: `get`, `list(from, to, status)`, `list_effective(user_id, since, until, category=None)` (resolved only, bounds inclusive), `save_evaluation(tx_id, Evaluation)`, `annotate(tx_id, purpose, beneficiary, effective_amount, source, explanation, confidence)`, `set_pot`, `mark_resolved / mark_failed / bump_attempts`; `ledger` (get_or_create day, update); `plans` (latest, by version, history, next_version); `transfers` (create, undo once). *Tests:* `list_effective` excludes `unresolved`/`failed`; date bounds; `annotate` rejects `effective_amount > amount`; transfer undo twice → `already_undone`; isolation.
- **Step 3: conversation.** `agent_events`: `create` (dedup via the unique indexes → returns the existing row), `mark_asked`, `mark_answered`, `mark_handled`, `expire`, `pending_for(user_id)`, `open_question(user_id)`, `question_asked_today(user_id, date)` (only question types, by `asked_at` on that **Bucharest** date). `messages`: `save_user`, `save_assistant(text, speak_text, quick_replies, action_cards, ref_transaction_id, agent_event_id)`, `list(since, limit)` (exclusive `since`, oldest first). `notifications`: create, list (unread_only), mark_read. `agent_runs`, `tool_calls`. *Tests:* every valid transition works and every invalid one → `invalid_transition` (e.g. answered → pending); `question_asked_today` at 23:59 and 00:01 Bucharest time; messages `since` exclusive, `limit` respected, ordering.
- **Step 4: life context & savings.** `life_facts`: create, update, expire, delete, `list_active(on_date)` (confirmed, inside the validity window), `list_hypotheses`, confirm, reject. `signatures`: `replace_for_fact` (atomic), `list_active(effect=None)`. `pattern_rules`: create, list_active, record_hit, record_miss, deactivate. `receivables`: create, `update_status` (open → requested → paid; open/requested → cancelled), list_open. `pots`: create, update, close, list_active, `add_saved` (can't go below 0). `forecasts`: save, latest, `last_weekly_snapshot`. `baselines`: replace_all, list. *Tests:* every state machine (valid + invalid); a rejected fact is absent from `list_active`; an expired fact is absent after `valid_to`; `replace_for_fact` atomic (an exception halfway leaves the old set); `add_saved` below 0 → error; isolation for all.

**Done when.** Arch 15.3's service checklist is all ticked.

### B4 · `load_user_context` read model · P0 · 0.75 h · deps: B3, F2
**Goal.** One function that gives the engine, the context layer and the snapshot builder the same complete, immutable view of a user. David G. reviews it (it's what Claude "knows").
**Interface.** `async def load_user_context(db, user_id: int, today: date, history_days: int = 180) -> UserContext` in `app/services/context_loader.py`.

> **First (H+2): stub** returning `tests.builders.matei_ctx()` so the others can integrate.

- **Step 1: loader.** Fill every field of `UserContext`: profile, account, active goal + goal pot, income, fixed costs, planned events, active pots, open/requested receivables, confirmed facts active on `today` + hypotheses (separate), active signatures, active rules, plan preferences, cached baselines, resolved transactions of the last `history_days` as `TxView`, latest plan summary, latest forecast + last weekly snapshot, pending/asked agent events, question budget used today. Use a few batched queries (no N+1). *Tests (db):* a hand-built user with one row of everything → every field filled; counts match.
- **Step 2: exclusions & limits.** *Tests:* `valid_to < today` excluded; rejected facts excluded; hypotheses only in their list; transactions older than 180 days, `unresolved` or `failed` excluded; with two users seeded the other's data never appears; ≤ 10 SQL statements (count with an engine event listener); < 50 ms for the biggest persona (after B12); the result is frozen.

### B5 · Auth · P0 · 1 h · deps: F1, B3
**Goal.** Every request is tied to exactly one user via the Keycloak JWT; cron uses the `internal` role.
**Files.** `app/auth.py`.
**Error codes.** `missing_token`, `invalid_token`, `token_expired`, `invalid_issuer`, `invalid_audience`, `unknown_user` (401); `forbidden` (403); `auth_unavailable` (503).

- **Step 1: token verification (unit).** `JWKSCache`: discovery URL `KEYCLOAK_ISSUER/.well-known/openid-configuration` → `jwks_uri` → keys cached by `kid`; an unknown `kid` refetches at most once per 60 s. `verify_token(token) -> Claims`: RS256 only; `iss == KEYCLOAK_ISSUER`; `exp` and `nbf` with 30 s leeway; `azp ∈ {"savings-frontend", "savings-dev", "savings-cron"}` or `aud` contains `KEYCLOAK_AUDIENCE`. *Tests:* valid; expired; `nbf` in the future; wrong `iss` (`http://10.0.2.2:8080/realms/cashguard`); wrong `azp`/`aud`; `alg: none`; HS256 signed with the public key as the secret (algorithm confusion); unknown `kid` → one refetch → 401; JWKS unreachable with an empty cache → 503, with a warm cache → still validates (mock httpx with respx).
- **Step 2: dependencies (api).** `current_user` (Bearer header → claims → `users.keycloak_sub` → user), `require_internal` (realm role `internal`), `ws_user(token)`. *Tests:* no header / `Bearer` with nothing → `missing_token`; lowercase `bearer` accepted; valid `sub` not in the DB → `unknown_user`; an internal endpoint with a user token → 403, with a cron token → ok; WS with a bad token closes with 1008.

### B7 · WebSocket manager & events · P0 · 0.75 h · deps: B5
**Files.** `app/events.py`, `app/ws.py`.

- **Step 1: event builders.** One function per event of arch 5.2 (`agent_typing()`, `assistant_message(msg)`, `notification_new(n)`, `plan_updated(...)`, `transaction_resolved(...)`, `ledger_updated(...)`, `transaction_annotated(...)`, `forecast_updated(...)`, `receivable_updated(...)`, `pot_updated(...)`, `fact_hypothesis(...)`), each returning `{type, data, ts}`. *Tests (golden):* each builder's `data` keys equal the arch 5.2 table; `ts` is ISO UTC ending in `Z`; money serialised as numbers.
- **Step 2: manager + route.** `ConnectionManager` (`dict[int, set[WebSocket]]`, `connect`, `disconnect`, `push(user_id, event)`), `/ws?token=` (close 1008 on a bad token), ping every 30 s (configurable). *Tests (ws):* valid connect; bad token → 1008; a push to A reaches all of A's sockets and none of B's; disconnect removes the socket; a push to a user with no sockets is a no-op; a dead socket during a push is removed and the others still receive; the ping arrives (short interval in the test).
- **Step 3: push after commit.** `push_after_commit(session, user_id, event)` queues the event and sends it in the session's `after_commit` hook; a rollback drops it. *Tests:* commit → exactly one event; rollback → none; several queued events keep their order.

### B8 · Ingestion & processing pipeline · P0 · 1.5 h · deps: B3, B7 (+ stubs from danutu and David G.)
**Goal.** Arch F2 + F3 v0.8, exactly. This is the heart of the backend.
**Files.** `app/services/ingest.py`, `app/pipeline/processor.py`, `app/api/internal.py`.

- **Step 1: ingest.** `ingest(db, user_id, TxIn) -> tx_id`: validate (`amount > 0`, `direction ∈ {debit, credit}`, `items` well-formed, `merchant_raw` 1–200 chars, `occurred_at` ≤ sim today + 1 day), store `merchant_raw`, `mcc`, `items`, `description`, `direction`, `source`, `status = unresolved`, `effective_amount = amount`. Ingest never calls the engine or the AI. *Tests:* each validation rule rejects with `invalid_transaction`; a valid one is stored unresolved with `effective_amount == amount`; ingest makes no other calls (spy).
- **Step 2: claim, lock, per-transaction processing.** `process_user(user_id, trigger)`: `pg_advisory_lock(user_id)`; claim `unresolved` rows (`UPDATE … SET status='processing', locked_at=now() … FOR UPDATE SKIP LOCKED`); for each transaction, in its own SAVEPOINT: `context.evaluate_transaction` → `transactions.save_evaluation` → `engine.apply_transaction` → `push_after_commit(transaction.resolved, transaction.annotated)`; on error `attempts += 1` → back to `unresolved`, or `failed` with `error` when attempts ≥ 3. `/internal/recover` resets `processing` rows older than 5 min. *Tests (db_committed + spies):* 3 transactions → all resolved; the call order is evaluate → save → apply → push; evaluate raising for #2 → #2 `attempts = 1`, unresolved, #1 and #3 resolved; the 3rd failure → `failed` + error text; recover only touches rows older than 5 min.
- **Step 3: after the batch.** If a resolved credit is a salary → `engine.auto_save(...)` (danutu decides what's a salary; you just call it for every resolved credit and it returns `None` when it isn't one). Then once per batch: `engine.recompute_plan(reason="new transactions")` → `engine.forecast_goal` → push `plan.updated` / `forecast.updated`; `signals.detect` → day-level `agent_events`; `context.pick_question(today)` → at most one `agent_event(transaction_question, ref_transaction_id)`; if there are pending events and `trigger != "chat"` → `agent.run_proactive(user_id, event_id)`. *Tests:* nothing to process → no plan version bump and no events; a salary → `auto_save` called once, and a re-run doesn't call it again for the same transaction; a candidate from `pick_question` → one event + proactive called for `sim`/`cron` and **not** for `chat`; push happens after commit; a late transaction for a past day updates that day's ledger (via danutu's `apply`).
- **Step 4: concurrency + endpoints.** `/internal/process` (all users with unresolved rows), `/internal/recover`, both `require_internal`. *Tests:* two `process_user` for the same user at once (`asyncio.gather`) → every transaction applied exactly once and the balance is right; the endpoints without the role → 403.

### B9 · `POST /chat` & the agent run · P0 · 0.75 h · deps: B3, B7 (+ David G.'s `run_agent` stub)
**Files.** `app/api/chat.py`.

- **Step 1: the request.** Validate `text` (strip; 1–2000 chars) and `input_mode ∈ {text, voice, quick_reply}`; per-user busy check (in-memory set + `agent_runs.status = 'running'` as the truth after a restart) → 409 `agent_busy`; save the user message with its `input_mode`; update `users.language` with David G.'s `detect_language` (A11; until it exists, keep the current language); return 202 `{message_id, run_id}`. *Tests:* 202 + ids; stored with `input_mode`; empty / 2001 chars / unknown mode → 422; a second POST while one is running → 409.
- **Step 2: the background run.** Push `agent.typing` → `process_user(user_id, "chat")` → `agent.run_agent(user_id, "chat", text, input_mode)` → `messages.save_assistant(...)` with everything in `AgentResult` → push `assistant.message` → after-run hooks: `plan.updated` once if the plan changed, `forecast.updated`. Any exception → a fallback message from David G.'s `templates` in the user's language, `agent_runs.status = failed`, busy cleared. *Tests (ws):* order `agent.typing` → `assistant.message`; `plan.updated` only when the plan version changed; `run_agent` raising → the fallback is saved and pushed, run `failed`, the next POST accepted; an English message → `users.language = en` (once A11 lands).

### B6a · REST core endpoints · P0 · 1 h · deps: B3, B4, B5
**Files.** `app/api/schemas.py` (response models exactly as arch 9.3), `app/api/me.py`, `state.py`, `messages.py`, `notifications.py`, `plan.py`, `transactions.py`, `transfers.py`.
**Serialisation.** Money → JSON number rounded to 2 dp; dates `YYYY-MM-DD`; timestamps ISO UTC `Z`; labels (`purpose_label`, `category_label`) via David G.'s `app/i18n/labels.py`.

- **Step 1: schemas, `/me`, `/state`.** `GET/PATCH /me`; `GET /state` with every v0.8 field. *Tests:* body validates against the schema and has the keys of the 9.3 example; before onboarding `goal`, `plan`, `forecast` are `null`; `pending_question` set while a question is open and `null` after the answer; `PATCH /me` `language = "fr"` → 422; money is a number.
- **Step 2: messages, notifications, plan.** `GET /messages?since=&limit=`, `GET /notifications?since=&unread_only=`, `POST /notifications/{id}/read`, `GET /plan`, `GET /plan/history`. *Tests:* `since` exclusive, `limit`, order; `unread_only`; read → 204 and then unread count −1; isolation (another user's notification id → 404).
- **Step 3: transactions & transfers.** `GET /transactions`, `GET /transactions/{id}` (+ scores, matched fact/rule), `PATCH /transactions/{id}` `{purpose?, own_amount?, people_count?}` → same logic as `annotate_transaction` (call David G.'s handler function so there's one implementation) → danutu's `on_annotation_changed` → recompute → push `transaction.annotated`; `POST /transfers/{id}/undo`. *Tests:* `own_amount > amount` → 422 `invalid_own_amount`; `people_count = 0` → 422; a valid patch → plan version + 1 and the event pushed (spy); undo twice → 409 `already_undone`; isolation.
- **Step 4: route-table test.** Iterate `app.routes`; every `/api` route except `/health` (and `/sim/*` when enabled) returns 401 without a token. This test protects every future endpoint too.

### B12 · Seed loader · P0 · 0.75 h · deps: B2, B3, E12 (danutu), D1 + C1 + C4 (David G.)
**Files.** `app/db/seed.py` (`seed_all`, `seed_persona`), CLI `uv run python -m app.db.seed --reset`.

- **Step 1: static data + money profile.** Merchants and products (`data/merchants.json`, `data/products.json`); per persona from `data/personas/<id>/profile.json`: user (`keycloak_sub` = the realm user id), account, income sources, fixed costs, goal + goal pot, other pots, plan preferences; `sim_clock` = `SIM_START_DATE`. *Tests:* each persona exists with the right `keycloak_sub`; Matei's balance equals `profile.json`.
- **Step 2: life context + history.** Facts from `facts.json` → `signatures_for_fact` (David G.) → `signatures.replace_for_fact`; seeded rules; history transactions from `transactions.json` as `resolved` with their annotations. *Tests:* Andrei's occupation fact has `work_tool` signatures; Matei's Friday rule is present at 0.7 with 2 hits; the transaction count equals the file.
- **Step 3: derived state + reset.** Per persona: `engine.recompute_baselines` → `engine.recompute_plan(reason="seed")` → `engine.forecast_goal`, plus the "last week" snapshot (forecast as of 2026-06-08, flagged weekly). `--reset` deletes all user data first. *Tests:* seeding twice with `--reset` → identical counts; Ioana `household_scale = 2.1`; Matei's groceries baseline median 85 ± 10; a plan and a forecast per persona; Matei's last weekly snapshot ≈ 0.72 (exact value owned by danutu's calibration, E13).

### B10 · Simulator · P0 · 1 h · deps: B8, B12
**Files.** `app/sim/clock_store.py` (`SimClock` backed by `sim_clock`, cached in process, plugged into `app/clock.py`), `app/sim/scenarios.py` (loads `data/scenarios/*.json`), `app/api/sim.py`.

- **Step 1: clock + gating.** `SimClock.today()`, `set(date)`, `advance(days)`. When `SIM_MODE=false`, every `/sim/*` route returns 404 and is excluded from `/openapi.json`. *Tests:* `clock.today()` equals the stored sim date; advance(1); `SIM_MODE=false` → 404 for each route and absent from the schema.
- **Step 2: scenarios.** `POST /sim/transaction {scenario_id}` or `{merchant_raw, amount, mcc?, category?, items?, occurred_at?, persona?}` → ingest for the caller (or `persona`) → `process_user(trigger="sim")` → `{transaction_id}`; `GET /sim/personas`. *Tests:* unknown scenario → 404 `scenario_not_found`; a bad raw payload → 422; the transaction is already resolved when the response returns; times relative to the sim date resolve correctly.
- **Step 3: days + reset.** `next-day`: insert that day's scripted transactions → process → close-day (B11, or a no-op until B11) → advance the clock → day jobs in the arch §10 order. `jump {days}`: repeat. `reset`: delete all user data → `seed_all` → clock = `SIM_START_DATE` → push `plan.updated` to connected users. *Tests:* `next-day` advances exactly one day and calls the jobs in order (spy); `jump 5` crossing a Monday triggers the weekly snapshot once; `reset` twice → same counts and clock 2026-06-15.

### B6b · REST context endpoints · step 1 P0, the rest P1 · 1 h · deps: B3, C4/C9 (David G.)
**Files.** `app/api/receivables.py`, `forecast.py`, `pots.py`, `life_facts.py`, `products.py`, `life_profile.py`.

- **Step 1 (P0): receivables.** `GET /receivables?status=`, `POST /receivables/{id}/request-payment` (open → requested; notification "Cerere trimisă: 4 × 100 lei" / EN; push `receivable.updated`), `mark-paid` (→ paid; recompute plan + forecast), `cancel`. *Tests:* request-payment → status, notification text in RO and EN, event; twice → 409 `invalid_transition`; mark-paid → plan version + 1; isolation; 401.
- **Step 2: forecast, pots, products.** `GET /forecast` (+ weekly history), `GET /pots`, `GET /products` (David G.'s ranking C12; until it exists, catalogue order). *Tests:* shapes vs 9.3; isolation.
- **Step 3: life facts & profile.** `GET /life-facts?status=`, `POST` (validate with F2), `PATCH`, `DELETE` (removes its signatures), `POST /{id}/confirm`, `/{id}/reject` → after every write call David G.'s `on_fact_changed`; `GET /life-profile`, `PATCH/DELETE /life-profile/{key}` (soft notes only). *Tests:* invalid type/value → 422; POST → propagation called (spy) and, in one integration test, signatures created + plan version + 1; delete → signatures gone; reject → never re-proposed; isolation.

### B14 · Hosting & deploy · P0 (before the freeze) · 1 h · deps: B1
- **Step 1: server.** A VM with Docker; a reverse proxy with automatic TLS (e.g. Caddy) for `api.<domain>` and `auth.<domain>`; `KC_HOSTNAME = https://auth.<domain>` = `KEYCLOAK_ISSUER`; Keycloak proxy headers on; secrets only on the server (`.env` never committed); uvicorn 1 worker; cron container; `SIM_MODE=true`. Write the public URLs into `DGAREADME1.md` (closes Q22).
- **Step 2: smoke.** `scripts/smoke_remote.sh <base>`: health; token via `savings-dev`; `/me`; WSS connect + ping through the proxy (checks the Upgrade headers); `/sim/reset`; Scene A via David G.'s demo client. *Test:* run after every deploy; paste the output.

### B11 · Day jobs, internal endpoints, cron · P1 · 1 h · deps: B8, E11 (danutu), C7 (David G.)
**Files.** `app/pipeline/jobs.py`, internal endpoints, `cron/crontab`.

- **Step 1: close-day.** Finalise the ledger status with danutu's thresholds (E11); streak/milestone notifications; an overspend question **only if today's question is free** (`question_asked_today`), otherwise a quiet notification; recompute. *Tests:* every status boundary; idempotent per (user, date); the question-budget branch both ways.
- **Step 2: expiry jobs.** `expire_events` (pending > 48 h → `expired`), `expire_questions` (asked > 24 h → David G.'s `default_reading` → annotate with `source = default`, confidence 0.3 → event `expired`), `receivable_reminders` (open > 14 days → `receivable_reminder` event). *Tests:* 23h59m vs 24h01m; an answered question untouched; idempotent.
- **Step 3: weekly jobs + wiring.** `forecast_snapshot` (Monday), `weekly_reflection` (Sunday), `preemptive`, `infer_hypotheses` (Sunday, David G.'s C10); one internal endpoint per job with `require_internal`; crontab as arch §10; `/sim/next-day` calls them in the documented order. *Tests:* without the role → 403; each job idempotent.

### B13 · Notifications service · P1 · 0.5 h · deps: B3, C1 + A5 (David G.)
**Files.** `app/services/notifications.py` (`notify(db, user, type, params)` → row + `notification.new` after commit), `app/i18n/notifications.py` (RO + EN: overspend, plan_updated, streak, auto_save "Am pus 760 lei deoparte pentru Fond 10.000 · Anulează", payment_request_sent, receivable_reminder, goal_completed).
**Tests.** Every type exists in RO and EN and fills its params; amounts formatted with `app/i18n/format.py` (`10.000 lei`, `30,40 lei` in RO); **no template contains a banned phrase** (run David G.'s `find_banned` over all of them); `opens_chat` per type as designed; pushed only after commit.

### B15 · Audit logging & privacy · P1 · 0.5 h · deps: B3, A6 (David G.)
**Tests.** Every agent run writes `agent_runs` (trigger, model, iterations, status, error); every tool call writes `tool_calls` (input, output, status); **no system prompt or full transcript is stored** (Q27); the Anthropic key never appears in captured logs (`caplog` grep); failed runs keep the error text.
