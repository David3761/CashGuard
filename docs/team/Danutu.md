# Danutu: API tasks (engine & calculations)

> Assigned 2026-10-28 by David G. **Scope:** all the deterministic money maths in `app/engine/` (and `app/pipeline/signals.py`): daily budget, ledger, plans, what-if, household-adjusted baselines, anomaly features, the Monte Carlo goal forecast, drivers & options, pots / receivables / payday auto-save, day-level signals, and the persona data generator + demo calibration.
> **Not yours:** DB, endpoints, pipeline plumbing (bomboe); the context layer, the agent and the data files `merchants.json` / `priors.json` (David G.; you agree the priors numbers together).
>
> **Read first:** [`backend/docs/how-we-work.md`](../../backend/docs/how-we-work.md), [`backend/docs/work-breakdown.md`](../../backend/docs/work-breakdown.md) §0, and the architecture doc [`backend/docs/savings-coach-backend-architecture.md`](../../backend/docs/savings-coach-backend-architecture.md) §5.3.4–5.3.5, §6.7 (engine definitions + forecast), §15, §16.
>
> **Opening prompt for Claude Code:**
> *Read `backend/docs/how-we-work.md`, `backend/docs/work-breakdown.md` §0, the architecture doc sections listed in `Danutu.md`, and `Danutu.md`. We're doing task <ID>, step <n>. Follow the loop: plan → test analysis over every category → tests first (red) → implement (green) → `make check` → self-review → step report. Then stop and wait for my review.*

---

## 0. Overview

| Order | ID | Task | P | h | Status |
|---|---|---|---|---|---|
| 0 | S0 | Stubs of your §15 functions (fixtures) | P0 | 0.25 | ☐ |
| 1 | E1 | Calendar utilities | P0 | 0.5 | ☐ |
| 2 | E2 | Budget engine core (daily budget) | P0 | 1.5 | ☐ |
| 3 | E6 | Baselines + OECD household scale + essentials floor | P0 | 1 | ☐ |
| 4 | E7 | Anomaly features | P0 | 0.5 | ☐ |
| 5 | E12 | Persona data generator | P0 | 2 | ☐ |
| 6 | E3 | `apply_transaction` + ledger + re-annotation deltas | P0 | 1 | ☐ |
| 7 | E4 | `recompute_plan` + versions + reason | P0 | 0.5 | ☐ |
| 8 | E10 | Pots, expected receivables, payday auto-save | P0 | 1 | ☐ |
| 9 | E8 | Monte Carlo goal forecast | P0 | 2 | ☐ |
| 10 | E13 | Calibrate the demo numbers | P1 (before rehearsal) | 0.75 | ☐ |
| 11 | E11 | Day-level signals | P1 | 0.75 | ☐ |
| 12 | E9 | Drivers & options | P1 | 1 | ☐ |
| 13 | E5 | `simulate_plan` + solve mode | P1 | 1 | ☐ |

**Load:** P0 ≈ 10.25 h · total ≈ 13.75 h. "H+n" = *n hours after we all start building*.

**Your golden rule:** every function in `app/engine/*.py` except `service.py` is **pure**. It takes `app/domain` objects + `today` and returns `app/domain` results, with no DB, no clock, no network and no randomness without an explicit seed. `app/engine/service.py` holds the thin DB shells with the §15 signatures. Almost all your tests are unit tests on the pure functions.

---

## 1. What others need from you, and when

| Deliverable | Who needs it | Needed by |
|---|---|---|
| **S0 stubs** in `app/engine/service.py` (+ pure stubs) with the §15 signatures: `apply_transaction`, `on_annotation_changed`, `recompute_baselines`, `recompute_plan`, `forecast_goal`, `simulate_plan`, `own_share_estimate`, `auto_save`; pure `anomaly_features`, `household_scale` | bomboe (B8, B6a, B12), David G. (C6, A3) | **H+2** |
| `household_scale` + `compute_baselines` (E6) and `anomaly_features` (E7) | David G.'s `evaluate_transaction` (C6) | H+4 |
| Persona data files `data/personas/<id>/profile.json` + `transactions.json` (E12) | bomboe's seed loader (B12), David G.'s scenarios (D2) and acceptance tests (D3) | **H+5.5** |
| `apply_transaction`, `on_annotation_changed` (E3), `recompute_plan` (E4) | bomboe's pipeline (B8), David G.'s tool handlers (A3) | H+6 |
| `auto_save`, `receivables_expected`, `pot_contribution` (E10) | bomboe (B8), David G. (A3 `create_pot`) | H+6.5 |
| `forecast_goal` (E8) | the "78% → 71% → 77%" moment of the demo | H+8 |

## 2. What you need from others, and when

| From | What | For | Until it arrives |
|---|---|---|---|
| David G. | F1 repo skeleton (H+0.5) | everything | read the arch doc, sketch E1/E2 |
| David G. | F2 step 1: enums + `money.py` (H+1); steps 2–3: models, results, test builders (H+1.5) | every pure function | start E1 (plain `date`s) |
| David G. | C1: `data/merchants.json` (H+2.5) and `data/priors.json` (**agree the numbers together**) | E6 priors, E12 merchants | use a temporary priors dict in tests |
| David G. | C2 `normalize` (H+3) | the E12 test "every merchant_raw resolves" | skip that one test until it lands |
| bomboe | stubs of the services + `load_user_context` (H+2), real ones (H+5); F3 fixtures (H+3.5) | your `service.py` shells and db tests | write the pure parts first |
| David G. | `app/i18n/labels.py` + `format.py` (C1) | E9 option labels | return label keys |

---

## 3. Tasks

### S0 · Stubs · P0 · 0.25 h
Commit `app/engine/service.py` (and pure module skeletons) with the exact signatures of arch 15.1 and simple bodies: `recompute_plan` returns a fixed `PlanSummary`, `forecast_goal` returns probability 0.78, `apply_transaction` moves the balance by `amount` and day spent by `effective_amount`, `auto_save` returns `None`, `anomaly_features` returns `stat = 1` when `amount > 3 × median` else 0, `household_scale` returns 1.0. *Test:* each stub is importable and returns the documented type. **Tell bomboe and David G. when it's merged.**

### E1 · Calendar utilities · P0 · 0.5 h · deps: F2
**File.** `app/engine/calendar.py`.
- **Step 1.** `occurrences(day_of_month, start, end)` (a day past the month's end → the last day of that month), `paydays_between`, `months_between`, `days_in_month`, `iter_days(start, end)`, `next_monday(d)`. Every function documents whether its bounds are inclusive (use `(start, end]` for "from tomorrow to the deadline" and say so). *Tests:* day 31 in Feb 2027 → 28 Feb; day 29 in Feb 2028 (leap) → 29 Feb; day 30 in Feb 2027 → 28 Feb; `start == end`; `end < start` → empty; `iter_days` across 2026-10-25 (DST) has no gap and no duplicate; `next_monday` of a Monday (same day or next? document and test); property (hypothesis): results are inside the range, sorted, unique.

### E2 · Budget engine core (daily budget) · P0 · 1.5 h · deps: E1, F2 (E6, E10 stubs)
**File.** `app/engine/budget.py`: pure `compute_plan(inputs: PlanInputs, today) -> PlanResult | None`. Implements **arch 6.7**: the definitions table, weights, pins, buffer, essentials floor, feasibility.
**Decisions written in code + tests:** income dated today is already in the balance once processed, so occurrences start tomorrow; fixed costs whose day has passed this month are already paid; the rounding residual of the daily split goes to the last day, so the sum is exact; no goal → `None`; deadline before today → `DomainError("deadline_passed")`.

- **Step 1: the money terms.** `PlanInputs` (built from `UserContext`) and one small pure function per term: `expected_income`, `fixed_remaining`, `events_remaining` (events covered by a pot excluded), `pot_contributions_remaining`, `receivables_expected` (from E10, stub ok), `still_to_save`, `available`, `buffer`, `free_money`. *Tests:* one test per term with hand-computed numbers; rent due later this month counted, rent due earlier not; an event with a pot not subtracted twice; goal reached → `still_to_save = 0`.
- **Step 2: the daily split.** Pins (exact amounts), weights (relative), the essentials floor (E6 stub until ready), feasibility (`rest_money ≥ 0` and every unpinned day ≥ floor), the list of infeasible days, the rounding residual. *Tests:* pinned day exact; Σ unpinned = free − pinned total; pinned total > free → infeasible; a day below the floor → infeasible + listed; buffer 0 vs 0.1 → free money differs by exactly 0.1 × available; **property:** any weights in [0.5, 3] → Σ budgets over the horizon unchanged, and Σ budgets == rest_money exactly.
- **Step 3: output + edges.** `today_budget`, `next_7_days` (date, budget, weight, pinned), `feasible`, `infeasible_days`. *Tests:* a golden Matei plan (record the values after the first run, then they're exact); deadline today → 1-day horizon; deadline passed → `deadline_passed`; negative balance → infeasible, no crash; no goal → `None`; determinism; every output Decimal at 2 dp; a 200-day horizon < 5 ms.

### E6 · Baselines, OECD household scale, essentials floor · P0 · 1 h · deps: F2, C1 priors
**File.** `app/engine/baselines.py` (pure) + `recompute_baselines` shell in `service.py`. Arch **5.3.5**.

- **Step 1: household scale.** `household_scale(facts, on_date) -> Decimal`: first adult 1.0, each other person aged 14+ 0.5, each child under 14 0.3; temporary members count only inside `[valid_from, valid_to]`; pets don't count. *Tests:* alone 1.0; couple 1.5; 2 adults + kids 7 and 11 → **2.1**; a 14-year-old counts 0.5; a temporary adult in July → 2.6 on 2026-07-10 and 2.1 on 2026-08-01; no adult fact → the user alone 1.0; property: ≥ 1.
- **Step 2: baselines.** `compute_baselines(txs, priors, scale, city, today) -> dict[Category, Baseline]`: personal median + MAD per transaction and the monthly totals per category on **effective** amounts over the last 180 days (bound inclusive), excluding `planned_event` and "not me"; the prior = `single_adult_prior × scale × city_index` for household categories only (arch 4.5), otherwise the plain prior; blend `(n·personal + 5·prior)/(n + 5)`; MAD = 0 → 0.25 × median. *Tests:* n = 0 → the prior × scale × city; n = 5 → the midpoint; n = 100 → ≈ personal; MAD fallback; electronics not scaled, groceries scaled; unknown city → 1.0; a 500 lei shared purchase counts as its 100; property: every baseline ≥ 0.
- **Step 3: floor, rescale, shell.** `essentials_floor(baselines, month)` (Σ monthly expected of essential categories / days in month), `rescale(baselines, old, new)`; shell `recompute_baselines(db, user_id)` writes `category_baselines` + `users.household_scale`. *Tests:* floor for Matei by hand; rescale 2.1 → 2.6 multiplies only household categories; shell (db) writes both and is idempotent.

### E7 · Anomaly features · P0 · 0.5 h · deps: E6
**File.** `app/engine/anomaly.py`: pure `anomaly_features(tx, baseline, history, monthly_disposable) -> AnomalyFeatures` (arch **5.3.4 step 4**).
- **Step 1.** `z = (amount − expected_median) / (1.4826 · MAD)` (MAD = 0 → 0.25 × median), `stat = clip(z/4, 0, 1)`, `novelty` (1 if merchant and category unseen in 90 days, 0.5 if only the merchant, else 0), `materiality = clip(amount / (0.10 · disposable), 0, 1)`, disposable ≤ 0 → 1. *Tests:* Matei's worked example (median 85, MAD 25, disposable 4 385 → z ≈ 11.2, stat 1, novelty 0, materiality 1); below the median → stat 0; each novelty case; seen exactly 90 days ago vs 91 (boundary, documented); disposable 0 and negative → 1, no division error; property: every output in [0, 1].

### E12 · Persona data generator · P0 · 2 h · deps: F2, C1, C2
**Files.** `scripts/generate_personas.py`; per persona `data/personas/<id>/config.json` (inputs you write) → generated `profile.json` and `transactions.json`. Personas and patterns: arch **16.1**. `as_of` 2026-06-15; history 2026-02-15 … 2026-06-14 (Bucharest); a fixed seed per persona.

- **Step 1: config + recurring streams + balances.** Config schema (income, fixed costs, goal, pots, streams); recurring transactions (salary on its day, rent, utilities ±10%, subscriptions exact); the start balance computed **backwards** so the final balance equals `profile.current_balance` exactly. *Tests:* salary and rent on the right day every month; start + Σ(credits − debits) == `current_balance` (Decimal, exact); no transaction after 2026-06-14 23:59 Bucharest.
- **Step 2: category streams + persona patterns.** Poisson visits × lognormal amounts around the persona median, with weekday/time preferences. Matei: Mega Image 3–4×/week on weekdays 12:00–14:00, median 85; a Friday team lunch 60–110 between 12 and 15; Glovo 2×/week in the evening. Ioana: Shop&Go almost daily, median 140, + Kaufland on Saturdays 300–500. Andrei: two sports streaming subscriptions, football tickets. Bianca: small amounts, irregular income (weekly tips). *Tests:* Matei 3–4 weekday-lunch Mega visits in each full week, Mega median 85 ± 8, a lunch every Friday within 60–110; Ioana Shop&Go median 140 ± 15; Bianca's income irregular (not on a fixed day).
- **Step 3: calendar, receipts, annotations.** Easter 12 Apr 2026 spike for Ioana; 1 Iunie gifts for Ioana's kids; 8 Martie flowers for Matei; receipt `items` on some transactions; annotations for the history (purpose from the category; Matei's two previous Friday lunches annotated as **answered**, to back the seeded 0.7 rule). *Tests:* Ioana's Easter week (6–11 Apr) > 1.5× an average week; the two answered lunches exist; items well-formed.
- **Step 4: quality.** *Tests:* running the generator twice → byte-identical files; every file validates against the F2 models; amounts positive with 2 dp; every `merchant_raw` resolves with David G.'s `normalize` (C2). **Tell bomboe and David G. when the files are merged.**

### E3 · `apply_transaction`, ledger, re-annotation deltas · P0 · 1 h · deps: F2, B3
**File.** `app/engine/ledger.py` (pure `apply`, `reannotate_delta`) + shells `apply_transaction(db, user_id, tx_id)`, `on_annotation_changed(db, user_id, tx_id, old, new)` in `service.py`.
**Rules.** The balance moves by the full `amount` (debit −, credit +). Day "spent" counts `effective_amount` unless the purpose is `planned_event` or it's a fixed cost. Credits are never "spent". A pot-funded transaction reduces `pot.saved` by `amount`. The ledger date is `occurred_at` in Bucharest time.

- **Step 1: pure.** *Tests:* debit 500 → balance −500, spent +500; re-annotation 500 → 100 → spent −400, balance unchanged; → `planned_event` → spent −effective and the pot −amount; salary credit → balance +, spent unchanged; rent → not spent; `23:30Z` in June → the next Bucharest day.
- **Step 2: shells (db).** *Tests:* a ledger row created when missing; applying an already resolved transaction is a no-op (guard); `on_annotation_changed` updates the right day (also a past day); called twice with the same values → no change.

### E4 · `recompute_plan`, versions, reason · P0 · 0.5 h · deps: E2, B3
**File.** `app/engine/plans.py` / `service.py`: load the context → `compute_plan` → save `plans` (version + 1, payload, feasible, `reason`, `trigger_ref`) → `PlanSummary(compare_to_previous=True)` (previous today budget, version).
- **Step 1.** *Tests (db):* versions 1 → 2 → 3; two concurrent recomputes for the same user → versions 2 and 3 with no unique-constraint failure (advisory lock or retry on conflict); `previous_today_budget` = the previous version's; reason + trigger_ref stored; no goal → no row and `None`.

### E10 · Pots, expected receivables, payday auto-save · P0 · 1 h · deps: E2, B3
**File.** `app/engine/savings.py` (pure) + `auto_save` shell. Arch **6.7** + D37.

- **Step 1: pots + receivables.** `pot_contribution(target, saved, deadline, today, paydays)` = (target − saved) / paydays left before the deadline; `receivables_expected(receivables, today, deadline)` with `p_repay` 0.9 until `expected_by`, −0.1 per full 14 days after, floor 0, and 0 if `expected_by` is after the deadline. *Tests:* a 3 000 pot by 15 Aug from 15 Jun (paydays 10 Jul, 10 Aug) → 1 500; deadline passed → 0; saved ≥ target → 0; `p_repay` at 0, 13, 14, 28, 140 days overdue.
- **Step 2: salary matching + amount.** A credit is a salary when it's within ±20% of an `income_sources` amount **and** ±3 days of its day of month. `auto_save_amount = min(planned_saving, balance − fixed costs due before the next payday − essentials floor × days to the next payday)`, `planned_saving = still_to_save / paydays_left`, never negative. *Tests:* each matching boundary (±20%, ±3 days, just outside each); the cap applied when the balance is low and not otherwise; no goal / goal completed → 0.
- **Step 3: shell.** `auto_save(db, user_id, income_tx_id) -> Transfer | None`: writes `transfers(kind = auto_save, pot_id, income_transaction_id)`, moves the money (balance −, goal pot +), sends the quiet notification (bomboe's `notify`), returns `None` when it isn't a salary or the amount is 0. Undo restores both. *Tests (db):* a salary → one transfer; the same income transaction again → no second transfer (idempotent); undo restores the balance and the pot; undo twice → error.

### E8 · Monte Carlo goal forecast · P0 · 2 h · deps: E1, E6, F2
**File.** `app/engine/forecast.py`: pure `forecast(inputs, n_paths=10_000, seed) -> Forecast` + shell `forecast_goal(db, user_id, plan_version)`. Arch **6.7 "Goal forecast"**.
**Seed:** `int.from_bytes(blake2b(f"{user_id}|{sim_date}|{plan_version}".encode(), digest_size=8).digest())` → `np.random.default_rng(seed)`. **Never Python's `hash()`**: it changes between processes and would make the demo number jump.

- **Step 1: the simulation.** Arrays of shape (paths, months). Income: deterministic for salaried users, bootstrapped from history when an irregular-income fact exists. Variable categories: bootstrap of monthly effective totals (last 6 months) × context multipliers (household scale ratio, temporary facts); < 3 months of history → lognormal(prior, CV 0.25). Events ± 20%; receivables Bernoulli(`p_repay`) in the month of `expected_by`; shocks Bernoulli(0.05) × lognormal(median 700), 0 with an emergency pot. The current month = actual effective spending so far + the expected rest. *Tests:* zero history → no crash; shocks off with an emergency pot; shape checks.
- **Step 2: outputs.** `probability = mean(savings_T ≥ target)`, p10 / p50 / p90, `expected_reach_date` (when the median path crosses the target, else `None`). *Tests:* target ≤ saved → 1.0; target 10× income → ≈ 0; p10 ≤ p50 ≤ p90; reach date `None` when p50 at the deadline < target; **property tests with common random numbers (same seed):** +500 income/month → probability ≥ before; adding a receivable → ≥; an emergency pot → ≥; an irregular-income persona has a wider p90 − p10 than a salaried one with the same mean.
- **Step 3: shell + snapshots + determinism.** `forecast_goal` saves `goal_forecasts` (plan_version, sim_date, outputs, reason); the first forecast on or after Monday 00:00 sim time is flagged `is_weekly_snapshot`, once per week. *Tests:* the same seed in **two separate processes** (subprocess) → the same probability (catches `hash()`); the snapshot flag once per week; 10 000 paths × 7 months < 100 ms (assert < 250 ms so CI isn't flaky).

### E13 · Calibrate the demo numbers · P1 (before rehearsal) · 0.75 h · deps: E8, E12, B12, C6, A3
**Goal.** Matei on 2026-06-15: **78%** (± 1 pp); after Mega 500 provisional **71%**; after "am luat și pentru colegi, suntem cinci" **77%**; the last weekly snapshot **72%**. Plus: Andrei's TV → inform, Bianca's TV → ask, Ioana's Shop&Go 350 → auto.
- **Step 1.** Tune **the data** (savings, income, goal amount, history), **never the formulas**. Write `tests/acceptance/test_demo_numbers.py` (golden): it fails if anyone later changes the engine or the data and breaks the demo. *Test:* the golden test itself, run against the seeded DB.

### E11 · Day-level signals · P1 · 0.75 h · deps: E2, B3
**File.** `app/pipeline/signals.py`: pure `detect_signals(ctx, ledger_today, plan, prev_forecast, forecast) -> list[SignalDraft]`.
**Thresholds 🟡 (confirm or change them, then they're final):** warning when spent > 0.9 × budget; overspend when spent > budget; under (at close) when spent < 0.5 × budget; `underspend_week` ≥ 20% under the week's plan; `category_cap` at 80% and 100% of a weekly cap (keep only the highest level per day); `infeasible_plan` when the plan turns infeasible; `goal_completed` once when `goal_pot.saved ≥ goal.amount`.
- **Step 1.** *Tests:* every boundary exactly (0.9, 1.0, 0.5, 20%, 80%, 100%) and one step either side; dedup per (type, date); `goal_completed` only once.

### E9 · Drivers & options · P1 · 1 h · deps: E8
**File.** `app/engine/options.py`.
- **Step 1: drivers.** Re-run with each non-protected, non-essential, non-household category −100 lei/month → percentage points gained; sorted descending. *Tests:* excluded categories never appear (Matei's protected concerts!); values ≥ 0; sorted.
- **Step 2: options.** Only when P < 0.6 or it dropped > 10 pp; at most 3, cheapest for the user first: (1) count the expected receivables, (2) move the deadline (soft goals only), (3) reduce the top driver by ≤ 25% of its baseline. Each is re-simulated. *Tests:* no options when P is fine; ≤ 3; each option's probability > the current one; no deadline option for a hard goal; reduction ≤ 25%; labels from i18n in RO and EN.

### E5 · `simulate_plan` & solve mode · P1 · 1 h · deps: E2, E8
**File.** `app/engine/simulate.py`.
- **Step 1: what-if.** Apply `changes` (arch 6.7 `simulate_plan` fields) to a **copy** of the inputs; run `compute_plan` + `forecast` (2 000 paths for speed). *Tests:* nothing saved (row counts unchanged); each change type moves the result the right way (+income → budget up; removing an event → budget up; adding a PS5 → probability down); `diff_vs_current` correct; a negative `est_cost` → `DomainError`; no changes → the same probability as the current forecast (same seed/paths).
- **Step 2: solve mode.** Given `target_daily_budget`: binary search for the earliest deadline giving ≥ the target (monotonic), and the largest goal amount for the same deadline. *Tests:* the returned deadline works and the day before doesn't; impossible (> 5 years) → `null` + reason; target ≤ current → the current deadline.
