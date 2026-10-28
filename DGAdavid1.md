# DGAdavid1 (David G.): API tasks (context layer, agent & LLM, data, demo & quality)

> Assigned 2026-10-28 by David G. **Scope:** the foundations everyone starts from (F1, F2), the whole **context layer** (`app/context/`, `app/i18n/`, the data files), the **agent** (`app/agent/`: Claude client, tools, executor, snapshot, prompts, loop, proactive questions, fallbacks, eval), the persona facts, the scenarios, the acceptance suite, the demo client, the runbook and the security review.
> **Not yours:** DB / endpoints / pipeline plumbing / auth / sim / hosting (bomboe); all money maths (`app/engine/`, danutu). You call their §15 functions, never re-implement them.
> We work on this file together with Claude, step by step, exactly as in [`backend/docs/how-we-work.md`](backend/docs/how-we-work.md): every step ends with a step report and **waits for your review**.
>
> **Read first:** `backend/docs/how-we-work.md`, [`backend/docs/work-breakdown.md`](backend/docs/work-breakdown.md) §0, and the architecture doc [`backend/docs/savings-coach-backend-architecture.md`](backend/docs/savings-coach-backend-architecture.md) §4.4–4.5, §5.3 (all), §6 (all), §7, F10–F16, §15, §16.

---

## 0. Overview

| Order | ID | Task | P | h | Status |
|---|---|---|---|---|---|
| 1 | F1 | Repo skeleton, tooling, config, clock, error envelope | P0 | 0.5 | ◐ F1.1 ✅ ([report](backend/docs/reports/F1.md)) |
| 2 | F2 | Shared domain types, enums, money helpers, test builders | P0 | 1 | ◐ 1a ✅ ([report](backend/docs/reports/F2.md)) |
| 3 | C1 | Fixed lists, RO/EN labels & formats, data files | P0 | 1 | ☐ |
| 4 | C2 | Merchant normalisation | P0 | 0.5 | ☐ |
| 5 | S0 | Stubs of your §15 functions | P0 | 0.25 | ☐ |
| 6 | C4 | Signature library + `signatures_for_fact` | P0 | 1.5 | ☐ |
| 7 | D1 | Persona life facts + Matei's seeded rule | P0 | 0.75 | ☐ |
| 8 | C5 | `life_fit` + the "because" | P0 | 1.5 | ☐ |
| 9 | C6 | `evaluate_transaction` | P0 | 1 | ☐ |
| 10 | C7 | Question policy | P0 | 1 | ☐ |
| 11 | A1 | Claude client wrapper + `FakeLLM` | P0 | 0.5 | ☐ |
| 12 | A2 | Tool schemas, registry, `tools_for` | P0 | 1 | ☐ |
| 13 | A5 | Prompts, banned-phrase checker, templates | P0 | 0.75 | ☐ |
| 14 | A4 | Snapshot builder | P0 | 1 | ☐ |
| 15 | A3 | Tool executor + every handler | P0 | 2 | ☐ |
| 16 | A6 | Agent loop | P0 | 1 | ☐ |
| 17 | A7 | Proactive runs (the spoken question) | P0 | 1 | ☐ |
| 18 | D2 | Scenario files | P0 | 0.5 | ☐ |
| 19 | D4 | Demo client (end-to-end scenes) | P0 | 0.75 | ☐ |
| | | ★ **Checkpoint: Scene A end-to-end** | | | |
| 20 | A9 | Deterministic fallbacks (LLM down) | P1 | 0.75 | ☐ |
| 21 | C8 | Learning rules | P1 | 1 | ☐ |
| 22 | C9 | Propagation on a fact change | P1 | 1 | ☐ |
| 23 | D3 | Acceptance suite (arch 16.3) | P1 | 1 | ☐ |
| 24 | A11 | Language detection + `speak_text` | P1 | 0.5 | ☐ |
| 25 | A10 | LLM eval set + runner | P1 | 1 | ☐ |
| 26 | D6 | Security & privacy review | P1 | 0.5 | ☐ |
| 27 | D5 | Demo runbook + rehearsal | P1 | 0.5 | ☐ |
| 28 | C10 | Hypotheses inference | P2 | 0.75 | ☐ |
| 29 | C11 | Calendar expected events | P2 | 0.5 | ☐ |
| 30 | C12 | Product ranking | P2 | 0.5 | ☐ |
| 31 | A8 | Live onboarding | P2 | 0.5 | ☐ |

**Load:** P0 ≈ 18 h · total ≈ 26.5 h. This is the heaviest of the three: bomboe has ~13.75 h of P0 and danutu ~10.25 h. The quickest relief would be moving **C1, C2, C7, D2** (≈ 3 h) to danutu. Your call.

---

## 1. What others need from you, and when

| Deliverable | Who needs it | Needed by |
|---|---|---|
| **F1** skeleton (pyproject, Makefile, app factory, config, clock, errors) | everyone | **H+0.5** |
| **F2 step 1** enums + `money.py` | bomboe (B2 CHECKs), danutu | **H+1** |
| F2 steps 2–3: models, results, `tests/builders.py` | everyone | H+1.5 |
| C1 `merchants.json` + `priors.json` (agree the priors with danutu) | danutu (E6, E12), bomboe (B12) | H+2.5 |
| S0 stubs: `evaluate_transaction`, `pick_question`, `default_reading`, `signatures_for_fact`, `on_fact_changed`, `learn_from_annotation`, `infer_hypotheses`, `build_snapshot`, `run_agent`, `run_proactive`, `detect_language`, `apply_annotation` (shared by A3 and bomboe's `PATCH /transactions`) | bomboe (B8, B9, B6, B11, B12) | **H+2** |
| C2 `normalize` | danutu (E12 test) | H+3 |
| C1 `app/i18n/labels.py` + `format.py`; A5 `find_banned` + templates | bomboe (B6a labels, B13), danutu (E9 labels) | H+4 |
| D1 persona facts; C4 `signatures_for_fact` (real) | bomboe (B12 seed) | H+4.5 |
| C6 + C7 real | bomboe's pipeline (B8) | H+6 |
| A6 `run_agent` + A7 `run_proactive` real | bomboe (B9, B8) → the checkpoint | H+8 |
| D2 scenarios | bomboe (B10 `/sim/transaction`) | H+6 |

## 2. What you need from others, and when

| From | What | For | Until it arrives |
|---|---|---|---|
| bomboe | service stubs + `load_user_context` stub (H+2); real (H+5); F3 fixtures (H+3.5); `ws.push_after_commit` + event builders (H+5) | your shells, A3 handlers, A4 | `tests/builders.py` contexts; pure-core unit tests |
| danutu | engine stubs (H+2): `recompute_plan`, `forecast_goal`, `apply_transaction`, `on_annotation_changed`, `own_share_estimate`, `recompute_baselines`, `anomaly_features`, `household_scale`; real E6/E7 (H+4), E3/E4 (H+6), E8 (H+8) | C6 (E6, E7), A3 (D18 recompute), C9 | the stubs |
| danutu | E12 persona files (H+5.5) | D1 cross-checks, D2 scenarios, D3 acceptance | hand-written mini personas in `tests/builders.py` |
| bomboe | B8 pipeline, B9 `/chat`, B10 sim, B5 auth, B7 WS | D4 demo client | the demo client against stubs |

---

## 3. Tasks (P0, in order)

### F1 · Repo skeleton & tooling · P0 · 0.5 h · deps: —
**Files.** `backend/pyproject.toml`, `.python-version` (3.12), `.env.example`, `Makefile`, `app/main.py`, `app/config.py`, `app/clock.py`, `app/errors.py`, `app/logging.py`, `backend/README.md`, `.gitignore` additions.

- **Step 1: project + tooling.** Dependencies from work-breakdown §0.1 (main + dev groups); ruff, mypy (strict for `app/domain`, `app/engine`, `app/context`), pytest config (markers `db`, `api`, `ws`, `live`, `slow`; default `-m "not live"`; asyncio mode auto); `Makefile` targets `dev`, `test`, `test-all`, `check`, `db-up`, `fmt`; `create_app()` with a router at `/api` and `GET /api/health`. *Tests:* health → 200 `{"status":"ok"}`; `make check` green on the empty project.
- **Step 2: config, clock, errors, logging.** `Settings` (pydantic-settings) with every variable of arch §3; a `Clock` protocol + `RealClock` (Europe/Bucharest) + `FixedClock` + `get_clock()` / `set_clock()`; `DomainError(code, message, status)` and the three exception handlers (arch 9.1 envelope); JSON logging that never prints secrets. *Tests:* `Settings` from env and `.env`; `SIM_MODE` accepts `true/1/false/0`; `FixedClock`; `RealClock.now()` tz-aware; `2026-06-14T21:30Z` → today `2026-06-15`; the DST day 2026-10-25 before/after 04:00; unknown route → 404 envelope; `DomainError` → its status + envelope; bad body → 422 envelope; `RuntimeError` → 500 envelope with no stack trace; `SecretStr` never appears in a logged settings dump.

### F2 · Shared domain types (`app/domain/`) · P0 · 1 h · deps: F1
- **Step 1 (deliver at H+1): enums + money.** `enums.py` (`StrEnum`, values exactly as in arch 4.4/4.5: `Category`, `Purpose`, `Beneficiary`, `Decision`, `Direction`, `FactType`, `FactStatus`, `FactSource`, `Persistence`, `SignatureEffect`, `SignatureOrigin`, `RuleKind`, `RuleSource`, `ReceivableStatus`, `PotKind`, `PotStatus`, `AnnotationSource`, `InputMode`, `AgentEventType`, `AgentEventStatus`, `Language`, `CoachStyle`, `TransferKind`, `ProductKind`, `Liquidity`); `money.py` (`to_money`, `split_share`, `share_each`). *Tests:* golden value lists per enum (copied from the arch doc); `to_money("1.005") == 1.01`, float `1.005` → 1.01 (via `str`), `-2.675` → −2.68, `7` → 7.00; `split_share` (500, 5) → (100, 400), (500, 3) → (166.67, 333.33), (100, 1) → (100, 0), (0.01, 3) → (0.00, 0.01), people ≤ 0 or a negative total → `ValueError`; `share_each(333.33, 2)` → 166.67; **property:** for any total 0.01–100 000 and people 1–50, `own + others == total` and both ≥ 0.
- **Step 2: models.** `models.py` (frozen Pydantic v2): `Item`, `TxView`, `LifeFact` with a typed `value` per `FactType`, `Signature`, `RuleMatch`, `RuleOutcome`, `PatternRule`, `Receivable`, `Pot`, `Goal`, `IncomeSource`, `FixedCost`, `LifeEvent`, `PlanPreferences`, `Baseline`, `Merchant`, `UserProfile`, `AgentEventView`, `UserContext`. Validation rules from work-breakdown F2. *Tests:* one pass + one fail per rule (`effective_amount > amount`; `amount ≤ 0`; child without age; occupation without title; `valid_to < valid_from`; temporary without `valid_to`; signature `amount_min > amount_max`, strength 1.2, multiplier 0, `explains` without category or hints, `expects_event` without amount; rule `from ≥ to`, weekday 8; naive datetime); frozen (assignment raises); JSON round-trip equal, with diacritics + emoji.
- **Step 3: results + builders.** `results.py` (`Evaluation`, `QuestionHint`, `FitResult`, `AnomalyFeatures`, `DayBudget`, `PlanResult`, `PlanSummary`, `Forecast`, `Driver`, `Option`, `SimResult`, `QuestionCandidate`, `RuleChange`, `PropagationResult`, `AgentResult`); `tests/builders.py` (`tx()`, `fact()`, `signature()`, `rule()`, `ctx()`, `matei_ctx()`, `andrei_ctx()`, `bianca_ctx()`, `ioana_ctx()`). Money in the API JSON is a number: give money fields a serializer (`float` in JSON mode) and document it. *Tests:* builders produce valid objects; a money field dumps as a JSON number with 2 dp; `mypy --strict app/domain` green.

### C1 · Fixed lists, labels, formats & data files · P0 · 1 h · deps: F2
- **Step 1 (deliver at H+2.5): merchants + priors.** `data/merchants.json` (~40 Romanian merchants: canonical name, aliases, category, MCC, typical basket, `multi_category`; the list is in work-breakdown C1), `data/priors.json` (single-adult monthly medians, basket medians and CV per category; city index Bucharest 1.0, Cluj 1.0, Iași 0.85; numbers **agreed with danutu**). *Tests:* both validate against a schema; every category is a valid `Category`; aliases unique across merchants after folding case and diacritics; eMAG / Altex / Carrefour / Auchan / Flanco / Diverta are `multi_category`; priors > 0; CV in (0, 2).
- **Step 2: labels + formats.** `app/i18n/labels.py` (`label(enum_value, lang)` for categories, purposes, beneficiaries, in RO + EN), `app/i18n/format.py` (`format_money`, `format_pct`, `format_date`). *Tests:* every value of those enums has an RO and an EN label (no missing key); `format_money(10000, "ro") == "10.000 lei"`, `(30.4, "ro") == "30,40 lei"`, `(1234.5, "en") == "1,234.50 lei"`, negative amounts; `format_pct(0.77, "ro") == "77%"`.
- **Step 3: products + calendar.** `data/products.json` (Pușculiță flexibilă, Cont de economii, Depozit 6 luni; fictional rates; `mock: true`), `data/calendar.json` (fixed-date events; configurable school start and Black Friday). *Tests:* schema; `min_months < max_months`; every product `mock: true`.

### C2 · Merchant normalisation · P0 · 0.5 h · deps: C1
**File.** `app/context/normalize.py`: pure `normalize(merchant_raw, mcc, script_category) -> NormalizedMerchant(merchant_id | None, name, category)`.
- **Step 1.** Fold case + diacritics; strip store numbers, city tokens and payment prefixes (`POS`, `PAYU*`, `SC`, `SRL`, `*ORDER`); longest alias match; MCC fallback table (work-breakdown C2); the script category always wins. *Tests:* `"MEGA IMAGE 0451 BUCURESTI"` → Mega Image / groceries; `"SHOP&GO 123"` → Shop&Go; `"PAYU*EMAG.RO"` → eMAG (multi); `"GLOVO*ORDER 8812"` → Glovo / food_delivery; `"Cărturești Verona"` and `"Carturesti Verona"` → the same; lowercase input; unknown + MCC 5411 → groceries, no merchant; unknown, no MCC → `other`; empty string → `other`; idempotent on canonical names; **property:** never raises on arbitrary Unicode (hypothesis).

### S0 · Stubs of your §15 functions · P0 · 0.25 h · deps: F2
Commit, with the exact arch 15.1 signatures and simple bodies: `context.service.evaluate_transaction` (→ `ask` with a provisional reading when `amount > 300`, else `auto`), `pick_question` (the first `ask` candidate if no question was asked today), `default_reading`, `signatures_for_fact` (→ `[]`), `on_fact_changed` (no-op), `learn_from_annotation` (→ `None`), `infer_hypotheses` (→ `[]`), `agent.snapshot.build_snapshot` (minimal text), `agent.loop.run_agent` (→ `AgentResult(text="Am primit: …")`), `agent.proactive.run_proactive` (the template question), `agent.language.detect_language` (keeps the current language), `agent.handlers.transactions.apply_annotation(db, user_id, tx_id, purpose, beneficiary, own_amount=None, people_count=None, others_will_repay=False, debtor_label=None, source=...)`. *Test:* each is importable and returns the documented type. **Tell bomboe and danutu when it's merged.**

### C4 · Signature library & `signatures_for_fact` · P0 · 1.5 h · deps: F2, C1
**Files.** `data/signature_library.json`, `app/context/library.py`.
- **Step 1: the library.** ~40 entries keyed by fact type + normalised value: occupations with synonyms (sports analyst / analist sportiv / jurnalist sportiv → TV, monitor, soundbar + sports streaming as `work_tool`; developer → laptop, monitor, software subscriptions; designer / photographer → camera, lens, Adobe; driver → fuel, car service; teacher → books, school supplies; student → books, education fees as `self_investment`); kids by age band (`expects_event`: school supplies Aug–Sep for ages 6–18, 1 Iunie for under 14; `explains`: kids' clothing and toys as `household_care`); pets; vehicle (fuel, yearly RCA, ITP, parking); activities (running shoes with a 180–300-day cycle, gym, cycling, gaming as `identity_joy`, photography, festivals, football); trips (travel inside the window → `planned_event`); priorities (`protects`). The household **multiplier** is E6's job: no scaling entries here. *Tests:* every entry validates against F2's `Signature`; no `health_pharmacy` `explains` entries; no duplicate keys.
- **Step 2: lookup.** `signatures_for_fact(fact, llm_signatures=None)`: library match by type + normalised value (synonyms, contains-match on folded text), `origin = library`. *Tests:* Andrei's occupation → the TV + streaming `work_tool` signatures; "Analist Sportiv" and "analist sportiv la o televiziune" match too; a kid aged 7 → school supplies + 1 Iunie; `priority: protected concerts` → a `protects` signature; an unknown fact with no LLM signatures → `[]`.
- **Step 3: Claude's signatures.** Validate each with F2; cap strength at 0.9; drop unknown fields, invalid purposes, `amount_min > amount_max`, and **any health/pharmacy signature** (sensitive), logging each drop; merge (the library wins on the same effect + category); `origin = llm`. *Tests:* "fac cosplay" + 2 valid signatures → kept, origin `llm`, strength ≤ 0.9; purpose `"good_purchase"` dropped; a health signature dropped; a library + LLM duplicate → the library one kept; empty / `None` → no crash.

### D1 · Persona life facts & Matei's seeded rule · P0 · 0.75 h · deps: F2, C4
**Files.** `data/personas/{matei,andrei,bianca,ioana,alex}/facts.json` (+ `rules.json` for Matei).
- **Step 1.** Facts per arch 16.1 (Matei: junior developer, lives alone, Bucharest, protected concerts, wants to cut food delivery; Andrei: sports analyst, remote, lives with his partner; Bianca: student + part-time barista, Iași, shared flat, irregular income; Ioana: accountant, Cluj, partner + kids 7 and 11; Alex: none). Matei's rule: restaurants, Friday 12:00–15:00, 60–130 lei → "Prânz cu echipa", confidence 0.7, 2 hits. *Tests:* every file validates; `signatures_for_fact` gives the expected signatures per persona; Ioana's facts → `household_scale` 2.1 with danutu's E6 (stub until it lands); no sensitive fact anywhere; Alex has none. **Tell bomboe when merged (B12).**

### C5 · `life_fit` & the "because" · P0 · 1.5 h · deps: C4, F2
**File.** `app/context/life_fit.py`: pure `life_fit(tx, ctx) -> FitResult(score, source, fact_id, rule_id, explanation_key, params)`. Arch **5.3.4 step 3**.
- **Step 1: signature match + saturation.** `match = 0.35·category + 0.20·merchant + 0.20·item + 0.15·amount_in_range + 0.10·time`; the amount term decays linearly to 0 at 2× outside the range; the item term is 1 when an item/description keyword matches (folded case and diacritics), else 0; the time term is 1 with no constraint. `saturation = min(1, days_since_last_similar / replacement_cycle_days)`, where "similar" = same category and (a keyword match or an amount within ±30%). `fit = match · strength · fact.confidence · saturation`. *Tests:* Andrei's TV with items → 0.855 ± 0.005; without items → 0.684; a previous TV 60 days ago with a 900-day cycle → ×0.0667; ≥ 900 days → ×1; amount 2× above the range → term 0, 1.5× → 0.5; a weekday mismatch → time 0; `"Televizor 65\""` matches `"televizor"`.
- **Step 2: other sources.** Precedent (a user-answered transaction at the same merchant, or same category with amount ±30% → `0.8 × (1 − |Δ| / amount)`), `expects_event` (window + category + amount within ±50% of expected), a partial rule (< 0.9 → its confidence), pots are handled in C6. `life_fit = max(...)`. Tie-break: higher score → confirmed over hypothesis → most recent. *Tests:* precedent similarity; Ioana's school supplies in August match; a hypothesis fact (confidence 0.5) caps the score; Bianca's TV → 0.
- **Step 3: the explanation.** `explanation_key` + `params` → i18n templates (RO + EN), e.g. "Nu te-am întrebat de televizor pentru că mi-ai spus că ești analist sportiv." *Tests:* the text exists in both languages and mentions the fact; **property:** score ∈ [0, 1]; deterministic for the same inputs.

### C6 · `evaluate_transaction` · P0 · 1 h · deps: C2, C5, danutu's E6 + E7
**Files.** `app/context/evaluate.py` (pure `evaluate(ctx, tx) -> Evaluation`), `app/context/service.py` (the §15 shell: load the context → evaluate → return; bomboe's pipeline saves it). Arch **5.3.4 steps 1–7**.
- **Step 1: normalisation + hard filters.** Normalise (C2); hard filters in order: below `max(50 lei, 1% of monthly income)` → `ignore`; credit → `auto`; a recurring bill (a fixed-cost match within ±10% and ±3 days, or a monthly recurrence for utilities/telecom/housing) → `auto`, `essential_living`; `health_pharmacy` → `auto`, never ask; an active pot match → `auto`, `planned_event`, `pot_id`; a classify rule ≥ 0.9 → `auto` with its outcome. *Tests:* 49.99 vs 50.00; with a 7 000 income → floor 70 (69.99 ignored, 70.00 evaluated); rent 2 200 (+10% exactly) → auto, 2 201 → evaluated; a credit; pharmacy 5 000 → auto, `essential_living`, no ask; Wizz Air with the trip pot → `planned_event` + `pot_id`; Matei's Friday rule at 0.9 → auto "Prânz cu echipa".
- **Step 2: score + decision.** `raw` and `unexplained` (E7 features + C5 life-fit); decision table (inform needs raw ≥ 0.5 **and** life_fit ≥ 0.6; ask needs unexplained ≥ 0.55); `question_hint` (reason key + params like the ratio "~6×"; `ask_what_item` only for multi-category merchants without items); `goal_impact = amount / max(remaining_to_goal, 1)`; provisional reading for `ask` (effective = amount, purpose `unknown`); explanation in the user's language. *Tests:* acceptance #1, #3–#7, #10, #11 (arch 16.3) on the builder personas; unexplained exactly 0.55 → ask, 0.5499 → auto; raw 0.5 + life_fit 0.6 → inform, 0.59 → not; `ask_what_item` true/false cases; a rule at 0.7 → no ask; 1 000 evaluations < 1 s.

### C7 · Question policy · P0 · 1 h · deps: C6, bomboe's B3
**File.** `app/context/questions.py`: pure `pick_question(candidates, ctx, now, sim_mode)`, `budget_state(ctx, today)`, `default_reading(tx)`. Arch **5.3.6**.
- **Step 1: budget, priority, quiet hours, weekly cap.** `priority = unexplained × goal_impact`; at most 1 question a day across every source; ~4 a week; quiet hours 22:00–08:00 (off in `sim_mode`). *Tests:* #12 (two candidates → the higher one asked, the other `ask_later`); today already used by an overspend question → `None`; 22:00 and 07:59 quiet, 08:00 allowed; `sim_mode` ignores quiet hours; the 5th of the week → `None`; deterministic tie-break (older transaction first).
- **Step 2: back-off, suppression, expiry, default.** Back-off after 2 ignored in a row (1 every 2 days for 7 days); a `suppress` rule → never; volunteered context free; `ask_later` expires after 48 h; `default_reading(tx)` → `unplanned_discretionary`, confidence 0.3, source `default`. *Tests:* back-off on and off again after 7 days; a suppress rule blocks; an already-answered transaction is skipped; `default_reading` values.

### A1 · Claude client wrapper + `FakeLLM` · P0 · 0.5 h · deps: F1
**Files.** `app/agent/llm.py`, `tests/fakes/fake_llm.py`.
- **Step 1.** `LLM.create(system, messages, tools)` → `AsyncAnthropic().messages.create(model=settings.ANTHROPIC_MODEL, max_tokens=8000, output_config={"effort": settings.ANTHROPIC_EFFORT}, system=…, tools=…, messages=…)`, **no temperature**, no `tool_choice`; the optional refusal fallback (`betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`) behind a setting; timeout 30 s, `max_retries=2`; SDK errors → `LLMUnavailable` (rate limit, connection, 5xx) or `LLMBadRequest` (4xx). `FakeLLM(script)` returns scripted responses (content blocks incl. `thinking`, `text`, `tool_use`; `stop_reason`; `usage`) and records every request. *Tests:* the exact kwargs (no `temperature`, effort and model from settings, max_tokens 8000); fallback on → beta + `fallbacks`; FakeLLM order and "script exhausted" error; error mapping per SDK exception type. Live (`-m live`): one tiny real request → `end_turn`.

### A2 · Tool schemas, registry, `tools_for` · P0 · 1 h · deps: F2
**File.** `app/agent/tools.py`.
- **Step 1: input models + schemas.** One Pydantic input model per tool of arch 6.6 (incl. every 🆕 tool); JSON schema with `strict: true`, `additionalProperties: false` at every object level, `required`; descriptions that say **when** to use the tool (from arch 6.6 + the "typical calls" table). *Tests:* every schema validates as JSON Schema (jsonschema); `additionalProperties: false` everywhere (recursive); names unique snake_case ≤ 64; descriptions ≥ 40 chars and contain a "when" sentence; **no `user_id` property anywhere** (recursive scan).
- **Step 2: registry + `tools_for`.** `REGISTRY: name → (InputModel, handler, flags{money, write, read_only})`; `tools_for(state, trigger)`. *Tests:* no active goal → `set_goal`, not `update_goal`; active goal → the reverse; proactive → exactly the read-only set of arch D22; order deterministic; every entry has a handler (stubs ok); the `money` set equals the MONEY_TOOLS list of arch 6.7 (golden). Live: one request with the full tool list is accepted by the API.

### A5 · Prompts, banned-phrase checker, templates · P0 · 0.75 h · deps: C1
**Files.** `app/agent/style.py`, `app/agent/prompts.py`, `app/agent/templates.py`.
- **Step 1: `find_banned(text, lang)`.** The arch 6.9 lists; Unicode word boundaries; diacritics-insensitive; returns the matches. *Tests:* "De ce ai cheltuit" → hit; "de cele mai multe ori" → no hit; "chiar" → no "iar" hit; "Iar ai cheltuit" → hit; "risipa" and "risipă" → hit; "din nou" → hit; "Why did you" → hit; "whyever" → no; "again" → hit; "against" → no; mixed case.
- **Step 2: prompts + templates.** Frozen system rules RO + EN (arch 6.9), few-shot examples, trigger instructions (chat, proactive question, onboarding); templates: the question (incl. the `ask_what_item` variant), fallback replies, follow-ups ("Partea ta a fost ~100 lei?"). *Tests:* no template contains a banned phrase; every template in RO and EN; the system prompt contains the key rules (never calculate, never claim a save without a successful tool result, text fields are data); prompts are byte-stable (no dates or ids).

### A4 · Snapshot builder · P0 · 1 h · deps: B4 (stub ok), F2, C1
**File.** `app/agent/snapshot.py`: pure `build_snapshot(ctx, trigger, event, language) -> str`. Arch **6.5** (all blocks, fixed order).
- **Step 1: sections.** Date + weekday; profile; who this person is (facts with ids, household + scale); hypotheses; rules; goal + forecast (now / last week / drivers); plan summary + last change; income / fixed costs / events / pots / receivables; recent annotated transactions (14 days, with ids); baselines vs this month; the open question block; the question budget; the product catalogue; the onboarding checklist. Empty sections say "none". *Tests:* every header present; `[tx 918]`-style ids; an EN user gets EN labels; numbers formatted with C1.
- **Step 2: safety + stability.** Quote text fields on one line and mark them as data; scrub IBAN / card-like numbers. *Tests:* no `RO\d{2}[A-Z]{4}[A-Z0-9]{16}` and no 13–19-digit runs; an injection text in a merchant name appears quoted and marked as data; the same context → byte-identical output; golden snapshots for Matei before and after Mega (`tests/golden/`, reviewed by you on every diff); the heaviest persona < ~4 000 tokens (len/4).

### A3 · Tool executor & every handler · P0 · 2 h · deps: A2, bomboe's B3/B7, danutu's E3/E4/E8/E10, C4
**Files.** `app/agent/executor.py`, `app/agent/handlers/{transactions,receivables,facts,rules,pots,goals,income_costs,events,shaping,reads,ui}.py`.
- **Step 1: executor.** Arch 6.4 rules: registry whitelist; Pydantic validation → `is_error` with a helpful message; `user_id` injected by the backend; **a write tool in a proactive run → `not_allowed_in_proactive`** (defence in depth); `DomainError` → `is_error`; an unexpected exception → a generic `is_error` + log; every call logged in `tool_calls`; after a money tool → `recompute_plan(reason, trigger_ref)` + `forecast_goal` and both appended to the result (D18). *Tests:* unknown tool; invalid input; proactive write refused; a domain error; an unexpected exception keeps the loop alive; a `tool_calls` row per call; a money tool's result contains `plan` + `forecast` with the previous values.
- **Step 2: transactions & receivables.** `get_transaction`; `annotate_transaction` → the shared `apply_annotation` (the transaction belongs to the user; effective = `own_amount` if given (wins over `people_count`), else `split_share(amount, people_count)`, else danutu's `own_share_estimate` with `estimated: true`, clamped ≤ amount; a receivable when `others_will_repay` and the others' share > 0, `amount_each` for the card; danutu's `on_annotation_changed`; C8 `learn_from_annotation` (stub); mark the open question answered; push `transaction.annotated` / `receivable.updated` after commit); `create_receivable`, `cancel_receivable`, `mark_receivable_paid`; `offer_payment_request` (open receivable only → an action card; status unchanged). *Tests:* 5 people → 100 + 400 (amount_each 100); `own_amount` 120 → 120 + 380; `own_amount > amount` → error; `people_count = 1` → no receivable; both given → `own_amount` wins; neither → estimated, ≤ amount; a correction ("doar pentru mine") → receivable cancelled + the right ledger delta; another user's transaction → `not_found`; `offer_payment_request` on a paid receivable → error.
- **Step 3: life, plan and money tools.** `add_life_fact` / `update_life_fact` / `expire_life_fact` / `confirm_hypothesis` (validate the value; C4 signatures with Claude's `signatures`; C9 `on_fact_changed`, stub until C9); `create_pattern_rule`; `create_pot` / `update_pot` / `close_pot` / `link_transaction_to_pot` (danutu's `pot_contribution`); `set_goal` / `update_goal` (`goal_already_active`); income / fixed-cost / life-event tools; `shape_budget`; `record_slip_reason`; `record_reflection`; `update_life_profile` (soft notes only); `transfer_to_savings`; `complete_onboarding` (an error listing what's missing, incl. `life_context`). *Tests:* happy path + one invalid input + isolation for each; `set_goal` with an active goal → `goal_already_active`; `complete_onboarding` missing items listed.
- **Step 4: reads & UI.** `get_transactions`, `get_spending_summary`, `get_plan_status`, `get_goal_forecast`, `simulate_plan`, `suggest_savings_products`, `show_quick_replies`, `mark_event_handled`. *Tests:* read tools write nothing (row counts unchanged); `show_quick_replies` stores options on the run; `simulate_plan` saves nothing.

### A6 · Agent loop · P0 · 1 h · deps: A1–A5
**File.** `app/agent/loop.py`: `run_agent(user_id, trigger, user_message, input_mode) -> AgentResult` (arch 6.3 v0.8).
- **Step 1: the loop.** Load the snapshot + the last 20 messages; up to `MAX_AGENT_ITERATIONS`; on `tool_use` append `resp.content` **unchanged** + one user message with **all** tool results; `end_turn` → reply; `refusal` / `max_tokens` → fallback; the loop limit → fallback; `LLMUnavailable` → fallback with pending events left pending. *Tests (FakeLLM):* immediate `end_turn`; `tool_use` → result → `end_turn` (the 2nd request contains the assistant content verbatim + the tool result); 2 parallel `tool_use` → one message with 2 results, ids matching; `refusal`; `max_tokens`; 6 tool rounds → fallback; a tool error → `is_error` → then `end_turn`; the tool list is rebuilt each iteration (after `set_goal` the next request offers `update_goal`); thinking blocks preserved verbatim.
- **Step 2: post-processing.** `find_banned` on the final text (regenerate once, then the template); `speak_text` for voice input and proactive runs (A11 later; a simple version now); collect quick replies + action cards; `ref_transaction_id` from the open question; the fallback in the user's language. *Tests:* a banned phrase is replaced; `speak_text` set only when needed; quick replies and action cards returned; history capped at 20; an EN user gets an EN fallback.

### A7 · Proactive runs: the spoken question · P0 · 1 h · deps: A6, C7, bomboe's B3
**File.** `app/agent/proactive.py`: `run_proactive(user_id, event_id)`.
- **Step 1: transaction questions.** Event-specific instructions (the reason, `ask_what_item`, default quick replies); read-only tools; a template after 5 s or on any LLM error; save the message (`speak = true`, `speak_text`, `ref_transaction_id`, `agent_event_id`); mark the event asked; a notification (`opens_chat`). *Tests:* a message with ≥ 3 quick replies and `speak_text`; event `asked`; notification created; a timeout → the RO template "Am văzut 500 lei la Mega Image…", the EN one for an EN user; `ask_what_item` → "Ce ți-ai luat de la eMAG?"; the fake tries `annotate_transaction` → refused; > 18 words → a logged warning; the same event twice → no duplicate message.
- **Step 2: other events.** Overspend, weekly reflection, receivable reminder, goal completed (read-only; only question types use the daily budget). *Tests:* `goal_completed` doesn't use the question budget; overspend respects it.

### D2 · Scenario files · P0 · 0.5 h · deps: danutu's E12, C1
**Files.** `data/scenarios/{matei_mega_500, andrei_tv, bianca_tv, bianca_tv_noitems, matei_flight, matei_friday_lunch, ioana_shopgo_350, matei_shopgo_350}.json` (persona, merchant_raw, mcc, amount, items, time relative to the sim date).
- **Step 1.** *Tests:* each validates; the persona exists; the merchant normalises; evaluating each scenario on its seeded persona gives the arch 16.3 decision (ask / inform / auto / planned_event). **Tell bomboe when merged (B10).**

### D4 · Demo client · P0 · 0.75 h · deps: bomboe's B5, B7, B9, B10
**File.** `scripts/demo_client.py` (httpx + websockets).
- **Step 1: plumbing.** Login as a persona via `savings-dev` (password grant); open the WS and print every event with its timestamp; call `/sim/reset`, `/sim/transaction`, `/chat`; `--base` for local or hosted. *Tests:* runs against the local stack; prints the events.
- **Step 2: scenes + assertions.** `--scene A|B|C|D|E`, `--answer "…"`, `--llm-off` (chips path); **asserts the end state** (Scene A: effective 100, receivable 400, probability 77 ± 1, a spoken question received). *Test:* Scene A passes with the LLM on and off → **checkpoint**.

---

## 4. Tasks (P1, after the checkpoint)

### A9 · Deterministic fallbacks (demo safety) · P1 · 0.75 h · deps: A3, A5
**File.** `app/agent/fallbacks.py`.
- **Step 1.** Known quick-reply labels → deterministic actions when the LLM is down: "Doar pentru mine" → self / `unplanned_discretionary`; "Și pentru alții" → card "Câți ați fost?" [2] [3] [4] [5] [6+]; "5" → `apply_annotation(people_count=5, others_will_repay=True, debtor_label="colegi")`; "Ceva plănuit" → a matching pot, or ask which; "Prefer să nu spun" → `unknown` + suppress similar; EN labels too. *Tests:* Scene A via the chips with the LLM down → the same end state as the LLM path; unknown free text with the LLM down → a polite "can't process now" reply and **nothing changed**.

### C8 · Learning rules · P1 · 1 h · deps: F2, B3
**File.** `app/context/rules.py`. Arch **5.3.7**.
- **Step 1: `rule_matches`.** Category / merchant / weekdays / time window (inclusive) / amount range; never above 2× the max. *Tests:* each condition and its boundary; 2× max + 0.01 → no match.
- **Step 2: `learn`.** Two similar explanations (same category and weekday, time ±1 h, amount ±40%) → a new rule at 0.7; the third → 0.9; an explicit recurrence through the tool → 0.9 at once. *Tests:* +41% → none; a different weekday → none; the 2nd and 3rd confirmations.
- **Step 3: decay & corrections.** No hit in 60 days → −0.2; below 0.5 → inactive; a correction → misses + 1; 2 misses → inactive; `suppress` matches without classifying. *Tests:* each, plus acceptance #9.

### C9 · Propagation on a fact change · P1 · 1 h · deps: C4, C6, danutu's E6/E3/E4/E8
**File.** `app/context/propagate.py`: `on_fact_changed(db, user_id, fact_id) -> PropagationResult`. Arch **5.3.9**.
- **Step 1.** Replace signatures → danutu's `recompute_baselines` → re-evaluate the last 30 days **only where `annotation_source ∈ {auto, fact, default}`** → save the changed annotations + danutu's `on_annotation_changed` → `recompute_plan(reason="fact: …")` → `forecast_goal` → push events. *Tests:* Andrei's TV (auto) + the occupation fact → `work_tool`, explanation updated, ledger unchanged; the same TV after an **answer** → unchanged (precedence); Ioana's temporary mother → scale 2.6 in July only (#13); deleting a fact removes its signatures and re-evaluates; plan version + 1 with the reason; twice → no further change; 30 days < 200 ms.

### D3 · Acceptance suite (arch 16.3) · P1 (#1–#7 P0) · 1 h · deps: C6, A3, E8, B12
**File.** `tests/acceptance/test_context_acceptance.py`.
- **Step 1: cases #1–#7** on the seeded DB (`seeded_db`), through services + pipeline, with FakeLLM scripting the tool calls for the answers.
- **Step 2: cases #8–#15.** Together with danutu's `test_demo_numbers.py` (E13).

### A11 · Language detection & `speak_text` · P1 · 0.5 h · deps: A5
**File.** `app/agent/language.py`.
- **Step 1.** `detect_language(text, current)` (diacritics + RO/EN stopwords; short or ambiguous → current); `make_speak_text(text, lang)` (no emoji or markdown, ≤ 2 sentences, "77%" → "77 la sută" / "77 percent"). *Tests:* "Am luat si pt colegi" → ro; "I bought it for my colleagues" → en; "ok", "5" → current; "am dat split cu colegii" → ro; `speak_text` cases.

### A10 · LLM eval set & runner · P1 · 1 h · deps: A6, A3, D1
**Files.** `tests/eval/answers.jsonl`, `tests/eval/run_eval.py`, `tests/eval/reports/`.
- **Step 1: dataset.** 60–100 rows (mostly RO, some EN): persona, open question, utterance, expected tool calls + key args. 5–10 per row of the arch 6.6 "typical calls" table, plus multi-intent, negations, no diacritics, slang, numbers in words, off-topic. *Tests:* every row validates; personas and tools exist.
- **Step 2: runner.** Live run (`-m live`) → an accuracy table + a report file. Scoring: tool-name match, key-arg match with tolerance, multi-intent order-insensitive. *Tests:* the scoring unit-tested with FakeLLM. **Targets:** ≥ 90% overall, 100% on the demo rows. Costs money: run it after prompt changes only.

### D6 · Security & privacy review · P1 · 0.5 h · deps: most tasks
- **Step 1.** Check: isolation tests exist for every resource; internal + sim gating; no secrets in the repo (`git grep -n "sk-ant"`); prompt injection (snapshot + live eval); data minimisation; logs. **Output:** `backend/docs/reviews/security.md` (problem → why → fix → owner).

### D5 · Demo runbook & rehearsal · P1 · 0.5 h · deps: D4
- **Step 1.** `backend/docs/demo-runbook.md`: before the demo (reset, a warm-up LLM call, a WS check), timing per scene, the fallback steps, who clicks what, the backup video. Run one full dry run with the demo client and record the timings.

---

## 5. Tasks (P2, only if there's time)

### C10 · Hypotheses inference · P2 · 0.75 h
**File.** `app/context/inference.py`. *Tests:* fuel in ≥ 3 of 4 weeks → a vehicle hypothesis at 0.5; a monthly pet shop for 3 months → pet; monthly kindergarten → child; Decathlon + race fee → runner; a changed rent amount → "moved?"; weekly pharmacy → **no** hypothesis; an existing confirmed fact → no duplicate; a rejected one → never again; at most 1 new hypothesis per run.

### C11 · Calendar expected events · P2 · 0.5 h
**File.** `app/context/calendar_events.py`. *Tests:* Orthodox Easter by the Meeus Julian algorithm: 2024 → 5 May, 2025 → 20 Apr, 2026 → 12 Apr; fixed and configurable dates from `calendar.json`; events only for relevant facts (1 Iunie and school only with kids).

### C12 · Product ranking · P2 · 0.5 h
**File.** `app/context/products.py`. *Tests:* horizon < 3 months → the flexible pot first; 3–12 months → savings account; ≥ 6 months, fixed amount, stable income → term deposit first; irregular income → liquidity first; reasons in RO and EN; all marked mock.

### A8 · Live onboarding · P2 · 0.5 h
*Tests:* `complete_onboarding` without a life fact → an error listing `life_context`; with everything → `onboarded_at`, first plan + forecast; a scripted rich message through FakeLLM → the expected tool calls in order; onboarding rows in the eval set.
