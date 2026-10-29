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


### H-7 · bomboe B12 + danutu E12 · `data/merchants.json` (the merchant catalogue) · 🟢
- **Date / by:** 2026-10-29, DGAdavid1 (C1.2, merged b7d1739)
- **Why it was needed:** B12 seeds the `merchants` table from it, E12 generates each history transaction's `merchant_raw` from its aliases, and C2 normalises bank text with it.
- **What was done:** `backend/data/merchants.json`: 62 fictional-data entries for real Romanian brands, each with a **slug id** (D47), a canonical name, aliases (lower case, no store numbers, payment prefixes or cities; unique across merchants even reduced to letters + digits), a `Category`, a 4-digit text MCC, a 2-dp `typical_basket` and `multi_category` (exactly eMAG, Altex, Carrefour, Auchan, Flanco, Diverta: D32). The schema is `data/schemas/merchants.schema.json`, and a golden snapshot test pins every field.
- **Decisions taken on the owner's behalf:**
  - 62 merchants instead of ~40. The 9 additions are for the persona streams: DAZN, Wolt, World Class, iaBilet, Eventim, 5 to go, STB, Metrorex, CTP Iași. Enel is now **`ppc_energie`** (PPC Energie; `enel` is kept as an alias).
  - `merchants.id` is TEXT (the slug).
  - **Loaders must reject duplicate keys, NaN and Infinity, and read numbers as `Decimal`.** Use `tests/unit/datafiles.py`'s strict parser or the same rules. Plain `json.load` silently keeps the last duplicate key.
- **Merge instruction:** keep ours. B12 maps `id` → `merchants.id` (TEXT PK). E12 builds `merchant_raw` from an alias plus realistic noise (store numbers, city, `POS`/`PAYU*` prefixes, `BOLT.EU/O/…`), and its "every merchant_raw resolves" test then exercises C2. Check: the B12 seed counts 62 merchants; `pytest tests/unit/test_data_merchants.py` passes.

### H-8 · danutu E2–E10 + bomboe B3/B6 · the shared money helpers (`app/domain/money.py`) · 🟢
- **Date / by:** 2026-10-29, DGAdavid1 (F2.2, merged cb6161e)
- **Why it was needed:** every engine function and every service that touches money must round and split the same way.
- **What was done:**
  - `to_money(x)`: half-up to the cent, via `str()`, never -0.00; NaN, Infinity, |x| ≥ 10^10 (NUMERIC(12,2)) and non-machine strings → `ValueError`.
  - `quantize_cents(d)`: the same rounding, with no range limit (display uses it).
  - `to_decimal(x)`: exact, bounded.
  - `split_share(total, people) -> Split(own, others)` with `own + others == total` exactly; `share_each` is display only.
  - The `Money` pydantic field: `Decimal` in Python, a JSON number in JSON, so 31.20 is written `31.2`.
  - `parse_json(text)`: `json.loads` with `parse_float=Decimal`, NaN/Infinity rejected.
- **Decisions taken on the owner's behalf:** all arithmetic runs in the module's own decimal context, so a caller's context changes nothing. Scores are `float`, money is `Decimal` (D48).
- **Merge instruction:** keep ours, and never re-implement rounding. bomboe: read JSON request bodies that carry money with `parse_json` (pydantic and the stdlib parse long JSON numbers as floats first; 2-dp amounts are exact either way). danutu: use `split_share` / `to_money` in the engine and keep Monte Carlo internals in float/numpy. Check: `pytest tests/unit/domain/test_money.py`.


### H-9 · danutu E6/E8/E12 · `data/priors.json` (population priors) · 🟢
- **Date / by:** 2026-10-29, DGAdavid1 (C1.3, merged after 501e8f2). The numbers were "to agree with danutu" (C1); under D42 we chose them, so this entry asks danutu to confirm.
- **Why it was needed:** E6 blends personal history with priors (arch 5.3.5), E8 needs a fallback distribution with < 3 months of history, and E12 generates persona history.
- **What was done:** `backend/data/priors.json` + its schema. For each of the **19 variable** categories: `monthly_mean` (single adult, lei/month), `basket_median`, `basket_cv` (the spread of one transaction) and `cv` (the monthly total's spread, derived from purchase rate × basket). Also city indices (București 1.00, Cluj 1.00, Iași 0.85) and a default 1.00. Every number has its reasoning in `backend/docs/reports/C1.md` (old → new table), and plausibility tests check each persona's prior month against their disposable income (Matei 47%, Andrei 45%, Ioana 35%, Bianca 96%).
- **Decisions taken on the owner's behalf:**
  - **D51:** no priors for rent, utilities, telecom, subscriptions (they come from fixed costs).
  - **D50:** **kids is per child** (350 lei/month) × the number of children, not × household_scale.
  - Which categories scale with the household: use `app.domain.enums.HOUSEHOLD_SCALED_CATEGORIES`, not a flag in the file.
  - The city lookup goes through a key that ignores case, diacritics, punctuation, spaces and words like "Municipiul"/"Romania"/"sector" (tested on 19 spellings).
  - **To confirm (C1's readings):** the city index also applies to kids; the kids basket is per transaction (not × children); E8 may model the 8 lumpy categories (basket > month) as compound Poisson rather than lognormal; if lognormal, parameterise it by the **mean** with the file's `cv` (arch 6.7 uses a flat 0.25); seasonal categories (gifts, travel, kids, clothing) noted.
  - **Demo:** Ioana's real pattern (Shop&Go almost daily) gives ~4.300–5.800 lei/month of groceries against the 1.890 family prior, so Scene E must quote E6's computed figure, never "1.890".
- **Merge instruction:** keep ours unless danutu's calibration (E13) needs different numbers. Change a number and its golden entry in the same commit, and keep the plausibility tests green. **Load strictly** with `app.domain.money.parse_json` (Decimal, duplicate keys/NaN/Infinity/BOM rejected). Check: `pytest tests/unit/test_data_priors.py`.

> **Entries H-10 to H-14 were written in fast mode (D52).** Each comes from the agent's own proposal; the details are in the task reports under `backend/docs/reports/`.

### H-10 · danutu E3/E4/E5/E8/E10 · engine stubs in `app/engine/service.py` + pure E6/E7 · 🟢
- **By:** DGAdavid1 (S0 + C5 agents), 2026-10-29
- **What was done:** `app/engine/service.py` has his §15 functions with the exact signatures and stub bodies: `apply_transaction` (rule in the pure `ledger_delta`), `on_annotation_changed(old, new: TxView)`, `recompute_baselines`, `recompute_plan` (fixed PlanSummary), `forecast_goal` (0.78), `simulate_plan`, `own_share_estimate`, `auto_save` (None). Also **real** pure minimums: `app/engine/baselines.py` (`household_scale` OECD 1/0.5/0.3, `compute_baselines` with blend k = 5, MAD fallback, city index, kids per child D50) and `app/engine/anomaly.py` (`anomaly_features`, arch 5.3.4 step 4).
- **Merge instruction:** replace the stub bodies with E3/E4/E5/E8/E10; keep the signatures and return types. Keep or extend the pure E6/E7 (they pass Matei's z ≈ 11.2 and Ioana's scale 2.1). Who updates `pots.saved` on `link_transaction_to_pot` (E10) is open. Check: `tests/unit/engine/`.

### H-11 · bomboe B3 · implement `app/agent/ports.py` with Postgres · 🟢
- **By:** DGAdavid1 (A3 agent), 2026-10-29
- **What was done:** the tool handlers call bomboe's services only through typed Protocols in `app/agent/ports.py`; `tests/fakes/fake_services.py` is the in-memory reference implementation. Every method takes `user_id` and raises `not_found` for a missing id or another user's row.
- **Merge instruction:** implement the Protocols over Postgres and register them at startup (`set_services_factory(lambda db: Services(...))`). Method list (see `backend/docs/reports/A3.md`):
  - transactions: get/list/annotate/set_pot
  - receivables: create/get/cancel/mark_paid/list_open/open_for_transaction
  - life_facts: create/get/update/expire/confirm/reject/list_active
  - `signatures.replace_for_fact`, `pattern_rules.create`
  - pots: create/get/update/close; goals: active/create/update
  - income_sources, fixed_costs, life_events, slips, reflections (CRUD)
  - plan_preferences: get/save; `life_profile.set_note`
  - agent_events: get/open_question_for/mark_answered/mark_handled
  - `transfers.to_savings`, `users.mark_onboarded`, `plans.latest`, `forecasts.latest`, `products.list`, `tool_calls.log`

  WebSocket events collected in `run.pushes` are pushed after commit. Check: run A3's handler tests against the Postgres implementation.

### H-12 · bomboe B4/B8/B9 · `load_user_context`, `/chat`, the pipeline's proactive call · 🟢
- **By:** DGAdavid1 (A2/A4, A6/A7/A9 agents), 2026-10-29
- **What was done:** `build_snapshot(db, user_id, trigger, event_id)` is **async** and loads `app/services/context_loader.load_user_context` (B4, async, returns `app.domain.user_context.UserContext`). `run_agent(user_id, "chat", text, input_mode, run_id=…)` and `run_proactive(user_id, event_id, run_id=…)` are **async**; `run_proactive` returns `None` when nothing was said. `app/agent/wiring.py` is the adapter over our real pieces (tools_for once per run (D46), build_snapshot, A3's executor, the engine stubs).
- **Merge instruction:**
  - B4 fills the Q6 extras of `UserContext`: `recent_days` (14 days), `slips`/`reflections` (5 each), `life_notes`, `products`, `recent_questions`. It includes the asked question event (payload: reason, params, ask_what_item; `ref_transaction_id`) and its transaction.
  - B9 saves the user message first, then `await run_agent(...)`; a fallback reply marks the run failed.
  - B8 calls `await run_proactive(...)` for sim/cron triggers (not chat).
  - **Open (decide with bomboe):** `load_user_context` is async, but the context shells (`evaluate_transaction`, `pick_question`) are sync. Make the shells async when B4 lands (preferred), or B4 adds a sync variant. `AgentWiring.setup` takes a context loader until B4 exists (TODO(B4/B9)).
  - Check: `tests/unit/agent/test_scene_a.py`.

### H-13 · bomboe B12 + B10 · persona facts/rules + scenario files · 🟢
- **By:** DGAdavid1 (C2/C4/D1 and S0/D2 agents), 2026-10-29
- **What was done:**
  - `data/personas/<id>/facts.json` (`{"facts": [LifeFactDraft]}`, ids assigned by the DB; Alex empty) and `data/personas/matei/rules.json` (`{"rules": [PatternRule]}`: restaurants, Fri 12:00–15:00, 60–130 lei → "Prânz cu echipa", 0.7, 2 hits).
  - `data/signature_library.json` (45 entries) + `app/context/library.signatures_for_fact`.
  - `data/scenarios/<id>.json` (8 demo scenes + schema): the timestamp is the sim date + `day_offset` at `time` (Bucharest).
- **Merge instruction:** B12 reads these files with `money.parse_json` + `model_validate` and stores `signatures_for_fact(fact)` as `spending_signatures` (origin `library`). B10 `/sim/transaction {scenario_id}` reads the scenarios; `requires`/`expected` are for tests only. Check: Matei has 7 facts + 1 rule, Alex 0, Andrei exactly 2 `work_tool` signatures; `tests/unit/test_data_scenarios.py`.

### H-14 · bomboe B6b/B13 + David V. · texts, tools and limits to know · 🟢
- **By:** DGAdavid1, 2026-10-29
- **Notes:**
  - Romanian sentences use `app.i18n.format.format_money_in_sentence` ("80 de lei", "101 lei", "1 leu"); `format_money` is the compact display form ("500 lei").
  - B13 notification texts must pass `app.agent.style.find_banned` (every "iar"/"din nou"/"de ce", even neutral, D48). B9's error fallback is `app.agent.templates.fallback_reply("llm_down", lang)`.
  - The Claude API takes at most **20 strict tools** per request, so `tools_for` marks a priority subset strict, and the executor's Pydantic validation is the real guard.
  - **Claude runs on Amazon Bedrock (D53):** set `LLM_PROVIDER=bedrock`, `AWS_DEFAULT_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_SESSION_TOKEN` (the hackathon's temporary credentials) in the server's env/`.env`, never in git. The model id becomes `us.anthropic.claude-sonnet-5-5` automatically, and the Docker image needs boto3/botocore (already in `requirements.txt` via `anthropic[bedrock]`).
  - The A1 live tests (`uv run pytest -m live tests/eval -q -rs`) still assume an Anthropic API key; Bedrock was verified with a direct live call instead.

### H-15 · bomboe B3/B8/B9 · what the AI-safety controls expect from the platform · 🟢
- **By:** DGAdavid1 (AI-SAFETY agent, branch `dga-task/ai-safety`), 2026-10-29
- **Why it was needed:** the judges look at LLM safety; the agent now bounds what Claude can do, and three bounds need the platform's side.
- **What was done:** `backend/docs/ai-safety.md` (threat model, controls → files → tests) and `tests/unit/agent/test_ai_safety.py`. `transfer_to_savings` takes at most 100 000 lei and runs at most once per run (`transfer_limit`); a run makes at most 16 tool calls; a chat run waits for Claude at most 60 s; a user message is cut to 4000 chars; `LLM_MAX_CONCURRENCY` (default 4) caps the Claude calls in flight per process.
- **Decisions taken on the owner's behalf:** the 100 000 lei bound, the error code `transfer_limit` (HTTP 429 if it ever surfaces), the 60 s chat deadline.
- **Merge instruction:**
  - B3 `TransfersPort.to_savings`: refuse an amount above the current balance with `DomainError("insufficient_funds", …, 409)`; the agent can't see the balance in the tool call.
  - B8/B9: keep chat and proactive runs of one user serialised (`pg_advisory_lock(user_id)`, arch 11): `AgentWiring` keeps one `RunState` per user.
  - B9: `run_agent` never raises for an LLM failure, a timeout or a bug in the run; it returns the template and marks the run failed. The HTTP rate limiter (`app/security/ratelimit.py`, app-api branch) is the per-client layer in front of it.
  - Check: `uv run pytest tests/unit/agent/test_ai_safety.py`.
### H-16 · mobile (David V.) + whoever runs the hosted Keycloak · security changes to know · 🟢
- **By:** DGAdavid1 (platform-security agent), 2026-10-29
- **What changed:**
  - `/api/sim/*` needs the Keycloak realm role **`sim`**. `realm-cashguard.json` gives it to the five demo personas, so a fresh local Keycloak just works.
  - WebSocket close codes: **1008** bad token (refresh, then reconnect, as before), **4401** token expired while open (refresh, then reconnect), **4409** more than 3 sockets for the user (close the old ones), **4429** too many connects (wait, then reconnect), **1009** inbound frame over 4 KiB (the app never sends one).
  - REST: 429 `rate_limited` with `Retry-After` on `/api/chat` (10/min, 200/day) and `/api/sim/*` (30/min); 413 `payload_too_large` over 64 KiB; `PATCH /api/life-profile/{key}` values ≤ 2000 characters as JSON.
  - Only access tokens are accepted: sending an ID token now gives 401 `invalid_token`.
- **Merge instruction:**
  - Mobile: on 4401, treat it like 1008 (refresh the token, reconnect); back off on 4429/4409.
  - Hosted Keycloak seeded before this change (`--import-realm` skips an existing realm): in the admin console add the realm role `sim` and assign it to the personas; turn on brute force detection; set the password policy `length(12)`. Check: `POST /api/sim/reset` with a persona token → 204.
  - The prod overlay now refuses to start without `POSTGRES_PASSWORD`, `KC_DB_PASSWORD`, `KC_ADMIN_USER`, `KC_ADMIN_PASSWORD`, `KC_CRON_CLIENT_SECRET`, `KC_DEMO_PASSWORD` (≥ 12 chars) in `backend/.env`. An existing DB volume keeps its old password (`ALTER USER cashguard PASSWORD …`).
  - If the demo presenter clicks the simulator faster than 5 calls a minute, raise `RATE_LIMIT_SIM_PER_MINUTE`.


### H-17 · bomboe B3/B8 · the agent's tool ports on Postgres, and the last `_fallbacks` · 🟢
- **By:** DGAdavid1 (ports agent, branch `dga-task/pg-ports`), 2026-10-29
- **Why it was needed:** on the merged platform every Claude tool call returned `tools_unavailable` (H-11 was never built), and `PATCH /transactions`, `/life-facts` and `/products` still ran stand-ins.
- **What was done:** `app/agent/pg_ports.py` implements the 21 ports of `app/agent/ports.py` over your async services (ORM fallbacks, scoped by `user_id`, for slips, reflections and a few lookups). `platform.PlatformServices.execute_tool` runs each tool call in its own `unit_of_work()` (commit on ok, rollback on `is_error`); the handlers' WS pushes go out after the commit. Two small functions were added to your services: `life_facts.replace(db, user_id, fact_id, draft)` and `plan_preferences.save(db, user_id, prefs)` (whole-object writes: the agent merges changes itself, so it can also clear `valid_to` or unpin a day). `app/pipeline/ports.py` now calls our `apply_annotation` (A3), `on_fact_changed` (C9) and `rank_products` (C12); `app/pipeline/_fallbacks.py` is deleted. `tests/db/test_session.py`'s `real_sessions` uses the `engine` fixture's URL (the per-test isolation hid TEST_DATABASE_URL and it hung on the shared DB).
- **Decisions taken on the owner's behalf:** `transfer_to_savings` moves the money like the auto-save does (account − amount, goal pot + amount, a `manual` transfer); a slip's `amount_over` is that day's ledger overspend (0 without a ledger row); a reflection's `week_start` is this week's Monday; `mark_event_handled` on an already-answered event returns it as it is.
- **Merge instruction:** none beyond merging `dga-task/pg-ports`. The DB tests are in `tests/db/test_agent_pg_ports.py` (Scene A end to end, rollback on error, `add_life_fact` → C9, the pipeline's proactive run, `/chat` with a real tool call, every port with a foreign user).

### H-18 · danutu (E7) + bomboe (B3/B8/B9) + David V. (mobile) · the final hardening, done on your behalf · 🟢
- **By:** DGAdavid1 (boss + 4 agents, branch `dga-task/final-hardening`), 2026-10-29 morning
- **What was done:**
  - **danutu, `app/engine/forecast.py` (D57):** history draws scale relative to the history months' mean household, not today's. A temporary member present today used to shrink every later month (~20 %). `tests/unit/test_forecast.py`: the temporary-member test now expects July (her month) at 2.6/2.1 and August at 1.0, plus a regression test. The demo numbers didn't move.
  - **bomboe, B3:** `transfers.check_funds` (`SELECT … FOR UPDATE`) refuses a `transfer_to_savings` above the balance with `DomainError("insufficient_funds", 409)`; the payday auto-save is unchanged (its amount is already ≤ the balance). Closes H-15's balance item.
  - **bomboe, B8/B9:** proactive runs open an `agent_runs` row (`start_run` / `finish_run`, trigger `proactive`) and their tool calls are linked; a crash finishes it as `failed`. `/chat` now gets 409 `agent_busy` while a proactive run is running (seconds); the reverse (a proactive run while a chat runs) isn't guarded yet.
  - **bomboe, B4:** `context_loader` fills `recent_days` (14), `slips` (5), `reflections` (5), `life_notes`, `products`; `recent_questions` stays empty on purpose (it would switch on the weekly question cap).
  - **bomboe, B1:** cron runs as uid 10001 under supercronic v0.2.49 (SHA1-checked, linux-amd64 only); `make keycloak-sync` replaces H-16's manual Keycloak steps.
  - **David V.:** the app sends `X-App-Key` from `--dart-define=APP_API_KEY` (Chopper `HeadersInterceptor` + `EventStreamClient`), test `mobile/test/core/request/app_key_test.dart`. Written without a Flutter SDK: CI is the first compile.
- **Merge instruction:** keep ours. Check: `make check`; CI's `flutter analyze` + `flutter test` for the Dart part; an arm64 host needs the arm64 supercronic binary and its SHA1. The prod overlay now refuses to start without `APP_API_KEY`.
