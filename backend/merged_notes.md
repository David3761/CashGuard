# Merge notes: `engine-dev` (danutu, engine & calculations)

> What changed on this branch that matters when it's merged with the other branches (F1 skeleton, F2 domain types, bomboe's platform).
> Base: `api-development` @ `6214a5d` ("python setup"). Last updated: 2026-10-29.
> Scope: every task in `Danutu.md` (S0, E1–E13). The code is written **against the teammates' interfaces as the docs describe them**, as if F1/F2/B3/B4 already existed; §2 lists every assumed name.

## 1. Files added or changed

| Path | Task | Merge note |
|---|---|---|
| `backend/app/__init__.py`, `backend/app/engine/__init__.py`, `backend/app/pipeline/__init__.py` | — | Empty. F1 (David G.) also creates the `app/` package → trivial add/add conflict |
| `backend/tests/__init__.py`, `tests/unit/__init__.py`, `tests/acceptance/__init__.py` | — | Empty; make `tests` a package so `from app...` / `from tests.builders` work with `python -m pytest` from `backend/`. Drop them if F1 configures `pythonpath` instead |
| `app/engine/calendar.py` | E1 | stdlib only |
| `app/engine/stats.py` | E6, E8 | stdlib only: median/MAD, prior blend, monthly rate, `stable_seed` (blake2b) |
| `app/engine/anomaly.py` | E7 | primitives + the F2 wrapper `anomaly_features(tx, baseline, history, monthly_disposable)` |
| `app/engine/baselines.py` | E6 | household scale, baselines, essentials floor, rescale |
| `app/engine/savings.py` | E10 | pot contribution, `p_repay`, receivables, salary matching, auto-save amount |
| `app/engine/ledger.py` | E3 | `apply`, `reannotate_delta`, `counts_as_spent`, `estimate_own_share` |
| `app/engine/budget.py` | E2 | `PlanInputs`, the §6.7 terms, `compute_plan`, `plan_inputs(ctx)` |
| `app/engine/forecast.py` | E8 | `ForecastInputs`, `build_forecast_inputs(ctx)`, `forecast`, `is_weekly_snapshot` (numpy) |
| `app/engine/options.py` | E9 | `drivers`, `options` |
| `app/engine/simulate.py` | E5 | `apply_changes`, `simulate`, `solve` |
| `app/engine/service.py` | S0 + shells | **every engine function of arch 15.1**, real (not stubs): `apply_transaction`, `on_annotation_changed`, `recompute_baselines`, `anomaly_features`, `recompute_plan`, `forecast_goal`, `simulate_plan`, `own_share_estimate`, `auto_save` |
| `app/pipeline/signals.py` | E11 | `day_status`, `detect_signals` |
| `scripts/generate_personas.py` | E12 | stdlib only |
| `data/personas/{matei,andrei,bianca,ioana,alex}/config.json` | E12, E13 | generator inputs (Matei's are calibrated, see §4) |
| `data/personas/*/profile.json`, `transactions.json` | E12 | **generated**: re-run the script, never edit by hand (a test checks they match the generator) |
| `tests/unit/test_*.py` (16 files), `tests/acceptance/test_demo_numbers.py` | all | see §3 |
| `backend/requirements.txt` | — | **was empty (bomboe's), now filled**: numpy (E8) + pytest, hypothesis, ruff, mypy. Likely conflict when bomboe adds the platform deps: keep both; dev tools could move to `requirements-dev.txt` |

Not committed by this branch: the deletion of the old `api/` folder (rename `api/` → `backend/`) is in the working tree only.

## 2. Contracts

### ⚠️ Contract changes to announce (arch §15.1)
1. **Engine shells are `async def`** (the DB layer B2 and `load_user_context` B4 are async). §15.1 shows `def`. Every caller must `await`: bomboe's pipeline (B8), seed (B12), close-day (B11); David G.'s tool handlers (A3) and `on_fact_changed` (C9).
2. **`on_annotation_changed(db, user_id, tx_id, old, new)`**: `old` and `new` are the `TxView` before and after the annotation.
3. **`forecast_goal` returns `Forecast` with `drivers`, `options`, `previous_probability`, `last_week_probability`, `is_weekly_snapshot`, `sim_date`** filled; it saves the row itself.
4. **`auto_save` is idempotent per salary**: a second call for the same income transaction returns the existing `Transfer`.
5. **Pot-funded spending lowers `pot.saved` in `apply_transaction`** (Danutu.md E3). The arch F3 comment says `save_evaluation` does it ("pot match → pots.saved -= amount"). **Only one of the two may do it**, or the pot is drawn twice. Decide with bomboe.

### Interfaces of teammates' code this branch assumes
Names from work-breakdown F1/F2/B3/B4, Bomboe.md and arch 4.4/4.5/9.3/15. **Check each when merging**; a different name is a small fix.

| Module (owner) | Assumed |
|---|---|
| `app.domain.enums` (F2) | `Category`, `Purpose`, `Beneficiary` (`self`, `others`, `employer`, `shared`…), `Direction`, `FactType` (`household_member`, `income_pattern`), `FactStatus`, `SignatureEffect` (`protects`, `expects_event`), `ReceivableStatus`, `PotKind` (`goal`, `event`, `emergency`, `custom`), `PotStatus`, `TransferKind` (`auto_save`), `AgentEventType`; values = arch strings |
| `app.domain.models` (F2) | `TxView(id, amount, effective_amount, category, occurred_at tz-aware, direction, purpose, beneficiary, merchant_id, pot_id, status)` · `LifeFact(type, status, value, valid_from, valid_to)` · `HouseholdMemberValue(role, age)` · `Signature(effect, category, expected_date, expected_amount, strength)` · `Baseline` (= `category_baselines` columns) · `IncomeSource(id, source, amount, day_of_month)` · `FixedCost(id, name, amount, day_of_month)` · `LifeEvent(id, name, date, est_cost, type, status)` · `Goal(id, amount, deadline, status, hard_deadline)` · `Pot(id, name, kind, target, saved, deadline, goal_id, life_event_id, monthly_contribution, status)` · `Receivable(id, amount, debtor_label, expected_by, status, transaction_id)` · `PlanPreferences(weekday_weights {"Mon".."Sun"}, pinned_days {date: amount}, category_caps {category: weekly cap}, buffer_pct)` · `UserProfile(id, city, household_scale…)` · `Account(current_balance)` · `AgentEventView(type, status, event_date)` · `Transfer` · `UserContext` (next row). All frozen with Pydantic's `model_copy(update=…)` |
| `UserContext` (F2, filled by B4) | `profile, account, goal, goal_pot, income_sources, fixed_costs, life_events, pots, receivables, facts (confirmed, active today), hypotheses, signatures, plan_preferences, baselines {Category: Baseline}, transactions (TxView, last 180 d, resolved, ≤ today), latest_plan (PlanSummary), latest_forecast, last_weekly_snapshot (with .probability, .sim_date), agent_events` |
| `app.domain.results` (F2) | `DayBudget(date, budget, weight, pinned)` · `PlanResult(today_budget, days, next_7_days, feasible, infeasible_days, available, free_money, still_to_save)` · `PlanSummary(version, feasible, today_budget, previous_today_budget, next_7_days, reason)` · `AnomalyFeatures(z, stat, novelty, materiality)` · `Forecast(probability, p10, p50, p90, expected_reach_date, drivers, options, previous_probability, last_week_probability, is_weekly_snapshot, sim_date)` · `Driver(category, pp_per_100_lei)` · `Option(kind, label_key, params, probability, apply_hint)` · `SimResult(feasible, today_budget, avg_daily_budget, probability, diff_vs_current, solve)` · `SignalDraft(type, date, payload)` |
| `app.domain.money` (F2) | `to_money(x)` (half-up, 2 dp) |
| `app.errors` (F1) | `DomainError(code, message)`; codes used: `deadline_passed`, `invalid_change`, `no_goal` |
| `app.clock` (F1) | module-level `today()` |
| `tests.builders` (F2 step 3) | `tx(**fields)`, `fact(**fields)`, `ctx(**fields)` with defaults for every other field |
| `app.services.context_loader` (B4) | `await load_user_context(db, user_id, today)` |
| `app.services.*` (B3) | `transactions.get(db, user_id, tx_id)` · `fixed_costs.list(db, user_id)` · `accounts.adjust_balance(db, user_id, delta)` · `ledger.get_or_create(db, user_id, day)` → `.spent`, `ledger.update(db, user_id, day, spent=…)` · `pots.add_saved(db, user_id, pot_id, delta)`, `pots.update(db, user_id, pot_id, monthly_contribution=…)` · `plans.next_version(db, user_id)`, `plans.create(db, user_id, version=, feasible=, payload=, reason=, trigger_ref=)` · `forecasts.save(db, user_id, goal_id=, plan_version=, sim_date=, forecast=, reason=)` · `baselines.replace_all(db, user_id, list[Baseline])` · `users.update_household_scale(db, user_id, scale)` 🟡 · `transfers.create(db, user_id, amount=, kind=, pot_id=, income_transaction_id=)`, `transfers.get_by_income_transaction(db, user_id, tx_id)` 🟡 · `notifications.notify(db, user_id, "auto_save", params)` (B13) |
| `sqlalchemy` | `text`, `AsyncSession`; `recompute_plan` takes `pg_advisory_xact_lock(7331, user_id)` so concurrent recomputes get versions 2 and 3, never a unique-constraint error |
| `app.context.normalize` (C2) | `normalize(merchant_raw, mcc, script_category) -> (merchant_id, name, category)` (one E12 test) |
| `data/priors.json` (C1, David G. + danutu) | 🟡 `{"city_index": {"București": 1.0, …}, "categories": {"groceries": {"basket_median", "monthly_median", "cv"}, …}}`. **Shape and numbers to agree** |
| `app/i18n` (C1) | Option labels are **keys** (`option.count_receivables`, `option.move_deadline`, `option.reduce_category`) + params; the snapshot / app renders them in RO / EN |

## 3. Tests and how to run them

```bash
cd backend
.venv/bin/python -m pytest tests -q        # without teammates' code: 101 passed, 16 files skipped
.venv/bin/ruff check --line-length 110 app tests scripts
.venv/bin/ruff format --check --line-length 110 app tests scripts
.venv/bin/mypy --strict --ignore-missing-imports app scripts tests
```
- Every file that imports F2 / services starts with `pytest.importorskip(...)`: skipped now, they run by themselves after the merge.
- They were all run locally against a throwaway emulation of F1/F2/B3/B4 built from the table above (not in the repo): **393 passed, 1 skipped** (the C2 `normalize` test).
- mypy: 8 errors left, all caused by the missing modules (`Any` from `to_money` / F2 results, no `app.clock`). Re-check after F1/F2.
- Ruff sorts `app.domain` as third-party while it doesn't exist locally; the import grouping changes once F1/F2 are there.

## 4. Behaviour and decisions others depend on (🟡 = to confirm)

### E1 calendar
- `occurrences` / `paydays_between`: **`(start, end]`**; `iter_days` / `months_between`: **`[start, end]`**; `end < start` → empty; day 31 → last day of short months.
- 🟡 `next_monday(d)` returns `d` itself on a Monday.

### E2 budget (arch 6.7)
- Horizon `[today, deadline]`. Income **and fixed costs dated today count as already processed** (occurrences from tomorrow).
- `available = balance + spent_today + income + receivables_expected − fixed − events (not pot-covered) − pot contributions`. **`spent_today` is added back** (start-of-day view), so a coffee doesn't shrink today's own budget; the next recompute moves the change to the remaining days.
- Buffer = `buffer_pct × max(available, 0)`. Unpinned days get `rest × weight / Σ weights` rounded down to the cent; the residual goes to the last unpinned day, so Σ budgets = `free_money` exactly. `next_7_days` starts tomorrow (arch 9.3 example).
- Pot contributions in the horizon: the whole rest for pots ending by the goal deadline, else per-payday contributions inside the horizon.
- Golden Matei plan (synthetic inputs): available 34 580, free 26 322, today 131.61.

### E3 ledger
- Balance moves by `amount`; "spent" = `effective_amount` of debits except fixed costs (**±10 % and ±3 days** of a `fixed_costs` row), `planned_event`, transfers/savings; ledger day = Bucharest date.
- `estimate_own_share` = min(amount, the category's `expected_median`).

### E6 baselines
- 🟡 `household_member` facts list only the *other* people; the user is always the first adult (1.0). Only confirmed facts count.
- Window `[today − 180, today]`; counted: own-share debits, excluding `planned_event`, 🟡 "not me" = `beneficiary ∈ {others, employer}`, and income/transfers/savings.
- Personal monthly rate uses the history actually covered (a 4-month seed isn't read as 6 months).
- 🟡 `personal_mad` is stored **with the fallback** (MAD 0 → 0.25 × expected median).
- 🟡 Essentials floor categories: groceries, transport, health_pharmacy, household_goods (rent and utilities are fixed costs, already out of the daily budget).

### E7 anomaly
- Scores are `float`; 🟡 median 0 and MAD 0 → `z = inf` (⚠️ not valid JSON: cap before storing/sending); 90-day novelty window inclusive; merchant seen + new category → 0; history must be *before* the transaction.
- `monthly_disposable` = Σ income sources − Σ fixed costs.

### E8 forecast (D27)
- Seed = `stable_seed(user_id, sim_date, plan_version)` (blake2b), tested in two processes with different `PYTHONHASHSEED`.
- Arch formula, with these precisions: the current month counts the **full month's** income and fixed costs, what was already spent (own share **+ what was paid for others**, since it left the account) and the expected rest; previous months' leftover balance is not counted. `Savings_T = saved + max(0, Σ net)`, so a target already saved is certain.
- Bootstrap from **full calendar months** in the history (≥ 3), else lognormal(monthly_expected, CV 0.25). Household categories × scale(month)/scale(today) (temporary members). Shocks: Bernoulli(0.05) × lognormal(700, σ 0.6), off when an emergency pot has money. 🟡 Irregular income = a fact `income_pattern` with `value.regularity == "irregular"`.
- Fixed draw order (var, income, events, shocks, receivables) → property tests use common random numbers.
- ⚠️ **Known limit:** a payday auto-save inside the current month moves money into `goal_pot.saved` that the current month's income already counts, so it is counted twice until the month ends. Fix needs the month's auto-save transfers in `UserContext` (B4) to subtract them from `saved`.

### E9 options
- Drivers: −100 lei/month per cuttable category (never essential, household, kids/pets/housing/utilities/telecom/education or `protects` signatures), 2 000 paths, same seed.
- Options only when P < 0.6 or it dropped > 10 pp (exactly 10 → none); order: count receivables, move the deadline (soft goals only, +1/2/3/6 months, first that reaches 0.6), cut the top driver by 25 % of its monthly baseline. Kept only if better than now, max 3.

### E10 savings (D37)
- 🟡 Pot contribution is **per payday** (Danutu.md), not per month (arch 6.7 says `months_left`); rounded **up** to the cent. No payday left → the whole rest now. `pots.monthly_contribution` stores this per-payday value.
- `p_repay` = 0.9, −0.1 per full 14 days overdue, ≥ 0; only open/requested receivables with `expected_by ≤ deadline`.
- Salary = a credit within ±20 % and ±3 days (across month ends) of an income source.
- 🟡 Auto-save: planned saving = still to save / paydays in **`[today, deadline]` (today's salary counts)**; spare = balance − fixed costs due in `[today, next payday)` − floor × days to the next payday; rounded down.
- Undo of an auto-save is bomboe's `transfers.undo` + endpoint; the engine only writes a transfer row with everything undo needs.

### E5 simulate
- `changes` uses the `simulate_plan` tool fields; validation errors → `DomainError("invalid_change")` (unknown key, negative cost, buffer outside 0–0.3, weights outside 0.5–3). 2 000 paths, same seed for "current" and "changed".
- Solve mode bisects up to 5 years: the earliest deadline whose today budget ≥ target (the day before misses it) and the largest goal (cent precision) for the same deadline; neither → `reason: "target_not_reachable"`.

### E11 signals (thresholds 🟡 to confirm)
- warning > 0.9 × budget, overspend > budget (only one), under < 0.5 × budget at close (ledger status only, not an event), underspend_week ≤ 80 % at Sunday's close, category_cap 80 / 100 % of the weekly cap this ISO week (one per day, highest level), infeasible_plan when it turns infeasible (vs `ctx.latest_plan`), goal_completed when the pot reaches an active goal. Dedup per (type, date) against `ctx.agent_events`.

### E12 personas
- `config.json` (inputs) → `profile.json` + `transactions.json`; 2026-02-15 … 2026-06-14 Bucharest; `as_of` 2026-06-15; seeded, sorted JSON → byte-identical runs.
- `transactions.json` row: `ref, occurred_at (ISO with offset), amount, direction, merchant_raw, mcc, category (script category), items, description, stream, annotation {purpose, beneficiary, effective_amount, source auto|answer, label}`. `profile.json`: user, account, income_sources, fixed_costs, goal, goal_pot {name, saved}, pots, plan_preferences, history {from, to, as_of, start_balance}. **B12 (bomboe) loads these**: agree the shape.
- Andrei, Bianca and Ioana move a monthly amount to savings (`category: savings`), so their balances stay realistic. Andrei has an Altex purchase (electronics seen, eMAG never) and Bianca no electronics, for the TV scene's novelty values.
- Anomaly check on the generated data: Matei Mega 500 → stat 1, novelty 0, materiality 1 (as the arch). Ioana Shop&Go 350 → stat 0.96 and materiality 0.31 instead of 0.79 / 0.58, but the same raw score 0.57 → still `auto`. Tell David G. (C6 thresholds).

### E13 demo calibration
- Assumes Matei is user 1; seed = plan v1 + forecast on 2026-06-15 and a "last week" snapshot as of 2026-06-08 (history ≤ that day); Mega → v2, answer → v3; receivable expected 14 days later.
- Tuned **data only** (an April city break, a quiet fortnight in March, a lighter week 8–14 June). Result: **last week 71.5 %, before 78.8 %, provisional 69.8 %, answered 75.9 %** (script: 72 / 78 / 71 / 77).
- ⚠️ With the arch formula (the others' share leaves the account, the receivable comes back with p 0.9), the answer can only lift the probability to ~3 pp below "before", so 71 and 77 can't both be hit by tuning data. Options: accept ~70 / ~76 in the script, or change the model (for example, treat a fresh receivable as certain in the current month). **Team decision.**
- `tests/acceptance/test_demo_numbers.py` pins the recorded values (±0.0001) and the script's numbers (±1 pp before / last week, ±2 pp provisional / answered). The scene B/E decisions (TV inform/ask, Ioana auto) depend on C6 and live in David G.'s acceptance tests.

## 5. Open questions for the merge
1. `async` engine shells (§2.1).
2. Who draws pot-funded spending from the pot: `apply_transaction` or `save_evaluation` (§2.5).
3. `household_member` facts: only the others? (E6)
4. Essentials floor categories; "not me" beneficiaries (E6).
5. `priors.json` shape and numbers (E6/C1).
6. Exact B3 names marked 🟡 (`users.update_household_scale`, `transfers.get_by_income_transaction`, `fixed_costs.list`).
7. Pot contribution per payday vs per month (E10).
8. E11 thresholds.
9. E13: the 71 / 77 pair (§4 E13).
10. Auto-save double count inside the current month (E8 known limit).
11. `next_monday` on a Monday.
