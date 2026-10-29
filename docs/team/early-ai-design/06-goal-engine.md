# 06 — Goal Engine: Probability, Roadmap & Re-planning

> Owner: AI team (danutu leads the calculations). Pure Python + numpy, no LLM inside.
> Depends on: 03 (baselines, facts), 04/05 (annotated transactions, actions).

## 1. What it answers

- "Ai **81%** șanse să strângi 10.000 lei până la 31 decembrie, față de 72% săptămâna trecută."
- What the monthly roadmap is (how much to put aside each month, category envelopes).
- How a transaction / answer / life change moves that probability (**before → after**).
- What the options are when the probability drops ("mută termenul", "redu X", "folosește recuperările").

## 2. Inputs (all from the context bundle, see 07)

| Input | Source |
|---|---|
| `S0` current savings toward the goal | backend (account/pot balance) |
| Income schedule (amount, day, variability) | income facts + history |
| Fixed costs (rent, utilities, subscriptions, loans) | recurring transactions + facts |
| Variable categories: monthly distribution per category | **effective** amounts, context-adjusted (03 §6) |
| Pots (sinking funds) and their monthly contributions | pots |
| Receivables (amount, debtor, expected date, reliability) | receivables |
| Expected events (school, Christmas, Easter, vacation, RCA…) | `expects_event` signatures |
| Goal: target, deadline, priority, hard/soft deadline | goals |

## 3. Monthly cash-flow model

For each remaining month `m = 1..M` until the deadline:

```
FCF_m = Income_m − Fixed_m − Σ_c Var_{c,m} − PotContrib_m − Events_m + Receivables_m + Shock_m
Savings_T = S0 + Σ_m α · FCF_m           (α = share of free cash flow going to the goal; demo: 1.0)
P(goal) = P(Savings_T ≥ Target)
```

The current month uses **actual** spending so far + expected spending for the rest of the month.

## 4. Monte Carlo simulation

- **N = 10.000** simulated futures, vectorised with numpy (target < 50 ms per call).
- `Var_{c,m}`: sampled from the user's monthly effective totals for category `c` (bootstrap of the
  last 6 months; if < 3 months of history → lognormal around the context prior with CV 0.25),
  multiplied by active context multipliers (e.g. household scaling, temporary facts).
- `Income_m`: deterministic for salaried users; bootstrap from history for freelancers
  (this is why a freelancer's probability band is wider — and the agent explains that).
- `Receivables`: Bernoulli(`p_repay`) per receivable, `p_repay` = 0.9 default for colleagues,
  decays by 0.1 per 2 weeks overdue; realised in the month of `expected_by`.
- `Events_m`: known expected events with their estimated amounts (± 20% noise).
- `Shock_m`: unknown emergencies — Bernoulli(0.05) per month × lognormal(median 700 lei);
  set to 0 if an emergency fund pot covers it.
- Seeded RNG (`seed = hash(user_id, as_of_date)`) so the same state always returns the same number
  (important for a stable demo and for "vs last week").

### Outputs

```json
{
  "probability": 0.81,
  "savings_at_deadline": { "p10": 8650, "p50": 10900, "p90": 12400 },
  "expected_reach_date": "2026-12-04",
  "required_monthly_for_80pct": 760,
  "drivers": [
    { "category": "food_delivery", "sensitivity_pp_per_100lei": 2.1 },
    { "category": "restaurants",   "sensitivity_pp_per_100lei": 1.6 }
  ],
  "history": [ { "date": "2026-06-08", "probability": 0.72 } ]
}
```

`drivers` = how many percentage points the probability gains per 100 lei/month less in that
category — computed by re-running the simulation with each non-protected category reduced.

## 5. Re-planning rules per event type

| Event (from 05) | Effect on the model | Plan reaction |
|---|---|---|
| `UNPLANNED_TREAT` | actual spend in current month ↑ | absorb; spread the shortfall over remaining months; zero judgment |
| `SHARED_PURCHASE` | effective spend = own share; receivable added as expected inflow | probability rises vs provisional; reminder at +14 days if unpaid |
| `PLANNED_FUTURE_EVENT` | new pot with monthly contribution; later spending drawn from the pot | the vacation is part of the plan, not a deviation |
| `PERMANENT_CHANGE` (rent ↑) | `Fixed_m` rebased from `from_date` | full replan + options (see §6) |
| `HOUSEHOLD_CHANGE` | category baselines × equivalence ratio (03 §6.3) | full replan + options |
| `INCOME_CHANGE` | income rebased | full replan |
| `EMERGENCY` | essential one-off | replan; suggest emergency fund pot |
| `WORK_EXPENSE` | one-off; if reimbursable → receivable from employer | replan |
| `GIFT_OR_OCCASION` (yearly) | adds a recurring expected event next year | pot suggested 1–2 months ahead next time |

## 6. Options when the probability drops

If `P < 0.6` or it dropped by > 10 percentage points, generate up to 3 options, each with its
**own computed probability** (re-simulated), cheapest-to-the-user first:

1. Use expected inflows (receivables) → "Când primești cei 400 lei de la colegi: 79%".
2. Move the deadline (only if the goal is soft) → "Mutăm termenul la 15 februarie: 86%".
3. Reduce the most effective **non-protected** category (from `drivers`) by a realistic amount
   (≤ 25% of its baseline) → "Cu 150 lei/lună mai puțin la livrări: 82%".

Never propose cutting `essential_living`, `household_care`, or categories the user marked as protected.
The user chooses — the agent never changes the plan silently.

## 7. Roadmap object

```json
{
  "goal_id": "goal_01",
  "target": 10000,
  "deadline": "2026-12-31",
  "monthly": [
    { "month": "2026-06", "planned_saving": 650, "cumulative_target": 5850,
      "envelopes": { "groceries": 800, "restaurants": 350, "food_delivery": 200, "identity_joy": 250 } },
    { "month": "2026-07", "planned_saving": 760, "cumulative_target": 6610, "envelopes": { "...": 0 } }
  ],
  "pots": [ { "name": "Vacanță august", "monthly_contribution": 1000, "target": 3000 } ],
  "version": 14,
  "reason_for_last_change": "SHARED_PURCHASE on txn_0918"
}
```

Envelopes are allocated in priority order: fixed → essentials → household → protected joy →
everything else. Every roadmap version stores `reason_for_last_change` so the UI can show
"de ce s-a schimbat planul".

## 8. Worked example (illustrative numbers, real ones come from the simulator)

Matei: target 10.000 lei by 31 Dec, `S0` = 5.200 on 15 June, median FCF ≈ 850 lei/month.

| Moment | Interpretation of the 500 lei | Probability |
|---|---|---|
| Before the transaction | — | 78% |
| Transaction arrives, unanswered | provisional: 500 personal discretionary | 71% |
| After "am luat și pentru colegi, suntem 5" | own 100 + receivable 400 (p = 0.9) | 77% |
| Colleagues pay | 400 realised | 78% |

Same mechanism, different life: for Andrei (sports analyst) the TV is classified as `work_tool`
without a question, but the 4.500 lei still lower the probability — the agent shows that neutrally
and, if he's an employee, asks once whether it's reimbursable.

## 9. Snapshots

Store `{date, probability}` every time it's computed plus one **weekly snapshot** (Monday 00:00) so
the UI can say "față de 72% săptămâna trecută". Snapshots live in the backend DB; the AI service
receives the last 8 weekly values in the context bundle.
