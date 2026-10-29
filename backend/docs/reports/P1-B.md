# P1-B (C12, C10, C11, A8): report

> Branch `dga-task/p1b-products-hypotheses-calendar`, worktree `.worktrees/p1b`, from `dga-final` (d79a962). Fast mode: no plan approval, no independent review. Every commit has a green `make check` (2 619 tests at the end).

## Commits

| # | Hash | What |
|---|---|---|
| 1 | cdef708 | **C12** `context/products.py`: `rank_products(ctx, products, today)` / `rank_offers(needs, products)` → `RankedProduct(product, score, reason_key, params, why_for_you {ro, en}, fits, mock)`. The `suggest_savings_products` handler is wired to it. |
| 2 | 7fdb1bc | **C10** `context/inference.py`: `infer_hypotheses(ctx, today, rejected)`, `question_for(draft, lang)`. The S0 stub in `context/service.py` is now a real shell. |
| 3 | d280d39 | **C11** `context/calendar_events.py`: `orthodox_easter`, `expected_events`, `event_signatures`, `calendar_fit`. `life_fit` has a new source, `fit.calendar`. |
| 4 | b66cd23 | **A8**: a FakeLLM-scripted onboarding run end to end, plus a live eval row. `add_life_fact` uses `source=onboarding` during onboarding. |

## Decisions to confirm

**C12 (products)**
1. **The horizon** is counted in whole calendar months. From 15 Jun, 14 Sep is 2 months and 15 Sep is 3; a past deadline is 0.
2. **Which product comes first** (the first rule that matches wins):
   - Irregular income → the flexible pot.
   - No goal → the flexible pot.
   - Under 3 months → the flexible pot.
   - 6 months or more, with a set amount, a steady income and a deposit that fits → the term deposit.
   - Otherwise → the savings account.
3. **What counts as steady or irregular income:**
   - *Irregular:* an `income_pattern` fact with `irregular: true`, or `employment.kind` ∈ {freelancer, self_employed, pfa, gig}.
   - *Steady:* not irregular, and either at least one income source or an explicit `irregular: false`.
   - With no income known yet, nothing is locked in (`top.no_steady_income`).
4. **The other products:**
   - In liquidity-first mode (irregular income, a short horizon or no goal) they're ordered by liquidity.
   - Otherwise the ones that fit the horizon come first, then the higher rate.
   - Scores: 0.9 (top), 0.6 (fits), 0.35 (reachable), 0.25 (a lock-in while the income is unknown), 0.1 (doesn't fit).
5. **Every result has `mock: true`**, whatever the row says.
6. **The handler's output:** `rank`, `score`, `fits`, `reason_key`, and `why_for_you` in the user's language.
   - The persona results: Matei and Ioana (6 months, salary) get the deposit first; Bianca gets the flexible pot first.

**C10 (hypotheses)**

7. **The detectors and their thresholds:**
   - fuel in ≥ 3 of the last 4 seven-day weeks
   - a pet shop in each of the last 3 thirty-day windows
   - kindergarten keywords (`gradinita`, `kindergarten`, `after school`) in each of the last 3 windows
   - sport gear (Decathlon or another sport merchant) plus race-fee keywords within 90 days
   - the latest rent more than 10% away from the one before, within 120 days, at confidence 0.4
8. **A kindergarten child is saved with `age: 4`.** F2 requires an age for a child; the card lets the user correct it.
9. **Sensitive data is excluded twice:**
   - `health_pharmacy` rows are dropped before any detector runs.
   - Only vehicle, pet, household_member, activity and housing can come out.
10. **Dedupe works per kind.** A confirmed fact, an open hypothesis or a rejected fact of the same kind blocks it:
    - **"Moved?"** is blocked only by a housing fact with `valid_from` on or after the change date. An old "rent" fact doesn't block it.
    - **Fewer than 3 open:** no new hypothesis while 3 are still open.
    - **Priority order:** vehicle > pet > child > runner > moved.
11. **The texts:** `text` is the first-person statement in the user's language ("Am mașină"). The card question comes from `question_for` ("Ai mașină?", "Te-ai mutat? Chiria pare să fie acum 2.400 de lei.").

**C11 (calendar). The no-double-counting rule:** a calendar item for category *c* around date *d* is **dropped when any active signature in the context already covers *c* in *d*'s month**, from any origin and with any effect.
- *Covers* means the signature's `time_window.months` contains the month, or its `expected_date` falls in it.
- So C4's library wins: `child_school` covers books in Aug–Sep and `child_1_iunie` covers kids in June. The calendar only fills the gaps: gifts on 1 Iunie, kids and clothing at school start, Christmas gifts and groceries.
- `life_fit` also keeps a single best source and never sums them.

12. **Child events** (1 Iunie 0–13, school 6–18, the ranges from calendar.json) need a confirmed child with a known age. They point at the first matching child fact, so one event per date.
13. **An event explains a category only when it says why:**
    - anything for a child event → `household_care`
    - gifts → `social_connection`
    - holiday groceries → `essential_living`
    - **Black Friday** explains nothing and produces no signature; it stays in `expected_events`.
14. **Strength 0.6** (× the child fact's confidence).
    - `calendar_fit` holds inside `[date − lead_days, date]`.
    - The amount factor is 1 up to 3× the usual basket and 0 at 6×. The usual basket is the baseline `expected_median`, else the `priors.json` basket.
    - `event_signatures` set `expected_amount` = 2× the usual basket.

**A8 (onboarding)**

15. **The live account's facts get `source=onboarding`** when `run.trigger == "onboarding"`; they stay `chat` otherwise.

## Gaps

- **There's no `life_facts.list_rejected` in B3.** The C10 shell uses it if present, and otherwise treats nothing as rejected, so "never again" wouldn't hold in the DB path. **Handoff to bomboe:** add `list_rejected(db, user_id) -> list[LifeFact]`.
- **Nobody calls `/internal/infer-hypotheses` (Sunday 20:00) or the WS `fact.hypothesis` push yet.** The caller saves the draft with `life_facts.create` and pushes `{fact_id, text, question: inference.question_for(draft, lang)}`.
- **`event_signatures` are meant to be computed on the fly** (engine / forecast), not stored. If B4 persists them into `ctx.signatures`, C5's own `expects_event` path scores them instead, and `calendar_fit` steps aside through the coverage rule. With `fact_id = None` that explanation would render an empty `„”`, so don't store them, or store them with a fact.
- **Eval:** there is no eval set yet. The A8 "eval row" is `tests/eval/test_onboarding_live.py` (`-m live`); it skipped here because this worktree has no provider configured.
- **`B4 load_user_context` is still async vs the sync §15 shells.** This is the same open point as C5-C7, and it applies to `service.infer_hypotheses` too.

## Integration notes

- **All new code is in new files** (`products.py`, `inference.py`, `calendar_events.py`, `test_onboarding.py`, …). The existing files touched:
  - `handlers/reads.py` (`suggest_savings_products`)
  - `handlers/facts.py` (the one-line source)
  - `context/service.py` (the `infer_hypotheses` shell)
  - `context/life_fit.py` (a `_calendar_fit` source and the `fit.calendar` template)
  - `tests/unit/agent/test_handlers_tools.py`, `tests/unit/context/test_service_stubs.py`
- **`suggest_savings_products`** reads `goals.active`, `income_sources.list`, `life_facts.list_active` and `products.list`. A product row without `kind` gets it from its liquidity, and string or int ids both work.
- **No existing test changed behaviour with the calendar source.** None of the Scene A–E dates falls in a relevant event window.
