# P1-A (C8, C9, A11): report

> Branch `dga-task/p1a-learning-propagation-language`, worktree `.worktrees/p1a`, from `dga-final` (d79a962). There was no plan approval (the boss's call). Every commit has a green `make check`: 2 613 tests pass.

## Commits

| # | Hash | What |
|---|---|---|
| 1 | c8d7213 | **C8** `context/rules.py`: `rule_matches`, `best_rule`, `learn`, `explicit_rule`, `decay`. The `learn_from_annotation` and `save_rule_change` shells are in `context/service.py`. |
| 2 | 391de27 | **C9** `context/propagate.py`:<br>- pure: `reevaluate`, `scale_windows`, `fact_scale_windows`, `fact_signatures`<br>- shells: `reevaluate_after_fact`, `on_fact_changed` |
| 3 | 472e6a7 | **A11** `agent/language.py`: `detect_language` and `make_speak_text`, wired into `loop.speak_text_for`, which serves both chat and proactive runs. |

## Decisions taken on the way (to confirm)

1. **What counts as similar (C8).** Two explanations are similar when they have:
   - the same category and the same Bucharest weekday;
   - times at most 60 minutes apart;
   - amounts within 40% of the *earlier* one (|new − old| ≤ 0.4 · old, so +41% is not similar);
   - the same purpose, given by the user (`answer` or `user_edit`).

   A new rule covers category + weekday. Its window runs from the earliest time − 1 h (rounded down to the hour) to the latest time + 1 h (rounded up). For 13:10 that gives 12:00–15:00. Its amounts run from 0.6 × the lowest to 1.4 × the highest. It has no merchant and **no label**: it reads as its category ("Restaurante, ca de obicei").
2. **Confirmations and corrections.**
   - A user answer on a transaction that a classify rule matches (or whose `matched_rule_id` is the rule) is a confirmation when the purpose is the same: hits + 1, and the 3rd hit lifts the rule to 0.9.
   - A different purpose is a correction: misses + 1. Two misses deactivate the rule.
   - Each transaction counts once (guarded by `last_hit_at`, set to the transaction's time).
   - Suppress rules are never confirmed or corrected.
3. **Decay is idempotent.** It removes 0.2 per full 60 days without a hit (or since creation). The count starts from the rule's *ladder* value: 0.9 for an explicit rule or one with ≥ 3 hits, else 0.7. It only ever lowers the confidence, so a job can run it every day. A seeded rule above its ladder value drops to ladder − 0.2 at its first decay.
4. **Rule matching moved** from `life_fit.py` into `rules.py`; C6 and C7 import it from there. Two C6 behaviours changed:
   - The time window's **end is inclusive** now (WB C8: "time-window bounds inclusive").
   - A **matching partial rule replaces precedents** in life-fit (5.3.2: a learned rule ranks above the answers it sums up). Without this, acceptance #9 read "Seamănă cu ce mi-ai explicat…" instead of "Prânz cu echipa".
5. **What propagation re-reads (C9).**
   - Only `annotation_source ∈ {auto, fact, default}` in the last 30 days, inclusive. `rule`, `pot`, `answer` and `user_edit` are never touched.
   - A change means one of these fields differs: category, purpose, beneficiary, effective amount, decision, source, explanation, matched fact / rule, pot.
   - **A past transaction never becomes a new question.** A re-read that would ask gets C7's default reading. A question that is already waiting (`ask` / `ask_later`) keeps its state.
6. **Signatures after a fact change.** The fact gets the library's signatures plus the Claude signatures it already had, on an effect + category the library doesn't cover. A fact that isn't confirmed gets none. So when the tool handler has already replaced the signatures, doing it again is a no-op.
7. **Two shells.** On the tool path the executor recomputes the plan once (D18), so:
   - `ports.LazyContext.on_fact_changed` now calls `reevaluate_after_fact` (no plan).
   - `on_fact_changed` (§15, for REST / B6b) also runs `recompute_plan(reason="fact: <type> <text>")` and `forecast_goal`.
8. **Household scale (#13).** `fact_scale_windows` compares the scale with the fact as it is now against the scale without it, from today − 30 days to today + 365 days. For Ioana's mother that gives 2026-07-01..07-31, 2.1 → 2.6. `PropagationResult.household_scale` is the scale *today*; I didn't add a windows field to `PropagationResult`.
9. **A11.**
   - **Scoring:** RO diacritics count 2, each RO / EN function or chat word counts 1. "am", "a" and "in" are in both lists. A language wins with a score ≥ 2 that is strictly higher than the other's. One word without diacritics keeps `current`.
   - **Spoken amounts:** no thousands separators. RO uses the "de" rule (`format_money_in_sentence`); RO bani are "1 ban", "5 bani", "80 de bani"; EN reads "29 lei and 80 bani".

## Integration notes (for the merge into `integration`)

- **Async.** bomboe's services and danutu's real engine are `async`. My shells are sync like the other `context/service.py` shells (the open B4 question). When the shells become async, put `await` on each call in these places:
  - `service.learn_from_annotation` and `service.save_rule_change`;
  - `propagate.reevaluate_after_fact` and `propagate.on_fact_changed`.

  The pure cores don't change.
- **bomboe's service functions used** (I checked them against `origin/bomboe`):
  - `pattern_rules`: `create`, `record_hit`, `record_miss`, `set_confidence`, `deactivate`;
  - `signatures`: `list_for_fact`, `replace_for_fact`;
  - `transactions`: `list_effective`, `save_evaluation`;
  - `life_facts`: `get`.

  **Engine** (`app.engine.service`): `recompute_baselines`, `on_annotation_changed(db, user_id, tx_id, old: TxView, new: TxView)`, `recompute_plan`, `forecast_goal`. No `ports.py` Protocol was extended.
- **Pre-existing mismatch.** `ports.EnginePort` / `LazyEngine.on_annotation_changed` pass `old, new` as **Decimal**, but the engine (S0 and danutu's real one) takes **TxView**. This needs fixing in the A3 handler path.
- **Pipeline (bomboe's F3).**
  - When a saved evaluation has `matched_rule_id`, call `pattern_rules.record_hit`, so decay sees the hit.
  - A daily job (B11) should run `rules.decay(ctx.rules, today)` and then `service.save_rule_change(db, user_id, old_rule, change)` for each change.
- **Not done.**
  - The open `transaction_question` event of a re-read transaction is not marked handled. C7 already skips it, because its decision is no longer `ask`.
  - `transaction.updated` / `plan.updated` WS pushes after propagation are left to the caller.
  - Ledger deltas go through danutu's `on_annotation_changed` only.
