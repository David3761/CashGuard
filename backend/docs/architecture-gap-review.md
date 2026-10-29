# Review: is `savings-coach-backend-architecture.md` complete end-to-end?

> **Reviewed:** bomboe's v0.7 (commit `34a892a`) · **By:** David G. (AI team), 2026-10-28
> **Team decision:** v0.7 is the architecture we build on. The old `api-ai` branch design is superseded; only its ideas are reused here.
> **Result:** v0.7 is a solid platform but **not complete** for the CashGuard pitch. The gaps below are folded into the architecture doc as **v0.8** (additions marked 🆕). Decisions and open questions: [`DGAREADME1.md`](../../docs/team/DGAREADME1.md).

---

## 1. Verdict

**Keep as is (it's good):** Postgres as the single source of truth · the transactions table as a queue with locks and retries · "code computes, Claude only picks which tool to call" (D6–D8) · executor security rules (user_id injected, whitelist, Pydantic, logging) · recompute inside every money tool (D18) · `simulate_plan` · read-only proactive runs (D22) · REST for commands + WebSocket for events · simulator with a fake clock · cron · the error-handling table.

**Not complete:** v0.7 describes a **daily-budget coach**. It notices that a *day* went over budget (at 23:55) and asks "what happened?". The pitch is a **context companion**. It looks at *one transaction* the moment it happens, checks it against *this person's life*, asks one question only when the life doesn't explain it, and re-plans the goal with the answer. The layer that correlates purchases with the person's life isn't in v0.7 at all, and that layer is what makes us different from Revolut.

### The 60-second demo, checked against v0.7

| Pitch moment | In v0.7? | Gap |
|---|---|---|
| A 500 lei Mega Image transaction appears | ❌ the simulator only plays whole days (`/sim/next-day`) | G-31 |
| The agent sees it's out of pattern *for this person* | ❌ only a day-level `overspend`, at close-day | G-10, G-04 |
| It asks one question, by voice | ❌ no voice anywhere (proactive text messages exist) | G-40 |
| "Am luat și pentru colegi" → the expense becomes 100 lei | ❌ no per-transaction effective amount; `slips` are per day | G-12 |
| "400 lei de recuperat" + payment request | ❌ no receivables | G-13 |
| Goal bar goes up / "81% vs 72% last week" | ❌ no probability; progress is `savings_pot / goal`, which a reclassification doesn't move | G-20 |
| "If every Friday is team lunch, it stops asking" | ❌ `patterns.py` is mentioned but never defined | G-11 |
| Vacation in August → dedicated pot split over the months | ⚠️ `life_events` reduce free money, but there are no pots | G-21 |
| "M-am mutat, chiria e mai mare" → full replan | ✅ `update_fixed_cost` + D18 | — |
| "Am cedat, mi-am luat adidași" → recalc, no reproach | ⚠️ works through `record_slip_reason`, but the doc's own example notification is "RESPECT THE PLAN! 🚨" | G-91 |
| TV = work tool for a sports analyst, a question for a student | ❌ nothing links life facts to purchases | G-01 to G-03 |
| A family of 4 spends more at Shop&Go, and that's normal | ❌ no household-aware baselines | G-04 |

---

## 2. How the whole process should work, on top of v0.7

```
 (0) LIFE MODEL 🆕    onboarding / seed / chat → life_facts → spending_signatures (what each fact predicts)
 (1) INGEST           simulator → transactions (unresolved)                                    [v0.7 F2]
 (2) APPLY            engine.apply: balance, day_ledger (on effective amounts)                  [v0.7 F3]
 (3) UNDERSTAND 🆕    context.evaluate_transaction:
                        merchant → category → learned rule? → pot? → life-fit against signatures
                        → deviation from the personal, household-adjusted baseline → anomaly score
                        → decision: auto | inform | ask | ask_later, plus an annotation with a "because"
 (4) RE-PLAN          engine.recompute_plan (effective amounts, receivables, pots)
                      + engine.forecast_goal 🆕 (probability, P10/P50/P90, vs last week)
 (5) ASK? 🆕          question policy: ≤ 1 question per day, the one that moves the goal most
                      → agent_event(transaction_question) → proactive run (read-only) phrases it
                      → WS assistant.message {speak: true} → the phone speaks it, the mic opens
 (6) ANSWER           voice → text → POST /chat → chat run with all tools:
                        annotate_transaction(people_count=5) + create_receivable(...) 🆕
                        (each money tool recomputes plan + forecast, D18)
 (7) SHOW             WS transaction.annotated 🆕 / receivable.created 🆕 / plan.updated / forecast.updated 🆕
                      → 500 → 100 lei, "400 lei de recuperat", the bar goes up, "77% (era 71%)"
 (8) LIFE CHANGES     "suntem 4 acasă", "m-am mutat", "în august merg în vacanță"
                      → fact tools 🆕 → signatures + baselines rescaled → full replan + options
 (9) LEARN            same explanation twice (or "în fiecare vineri") → pattern_rule 🆕 → no more questions
```

**Principle:** no purchase is good or bad. Its meaning is f(purchase, person, moment). Context changes the *interpretation* and *whether we ask*. It never makes the money disappear: a work-tool TV still lowers what's left for the goal, and the agent says so neutrally.

---

## 3. Gaps

**Priority:** **P0** the demo or the pitch breaks without it · **P1** the pitch is clearly weaker without it · **P2** nice to have, cut first.
**Owner:** **BE** bomboe (backend platform) · **CALC** danutu (engine & calculations) · **CTX** David G. (context layer, agent, LLM) · **FE** David V. (Flutter app).

### 3.1 Life context: correlating purchases with the person's life (the core)

| ID | P | Gap in v0.7 | Fix in v0.8 | Owner |
|---|---|---|---|---|
| G-01 | P0 | `life_profile.data` is a loose JSON (non_negotiables, triggers…). It has no source, confidence or validity, so it can't tell "the user said it" from "we guessed", can't expire "my mother-in-law stays a month", and can't explain anything. | `life_facts` table: type, value, source, status (hypothesis / confirmed / rejected / expired), confidence, valid_from/to. `life_profile` keeps soft coaching notes only. | BE table, CTX logic |
| G-02 | P0 | Nothing says what a fact means for spending. | `spending_signatures` per fact: `explains` (category / merchant / keywords / amount range → purpose), `scales_baseline` (× multiplier), `expects_event` (dated spend), `protects` (never cut first). A curated library covers common facts; Claude fills them in for free-text facts through a strict tool schema. | CTX |
| G-03 | P0 | No per-transaction correlation. | `life_fit(tx)` ∈ [0,1] = best match over signatures / rules / pots / precedent × fact confidence × saturation. The best match writes the **"because"** ("Nu te-am întrebat pentru că mi-ai spus că ești analist sportiv"). | CTX |
| G-04 | P0 | "Normal" isn't defined per person, and the **essentials floor** in the engine rules is used but never defined. | Per-category baselines (median + MAD on *effective* amounts) blended with a context prior: `(n·personal + 5·prior)/(n+5)`. Household scaling with the OECD scale (1 / 0.5 / 0.3, so 2 adults + 2 kids = 2.1), rescaled instantly when the household changes. Essentials floor = Σ essential-category baselines per day. | CALC |
| G-05 | P1 | A 2nd TV two months after the first looks exactly like the first. | `replacement_cycle_days` on signatures → saturation lowers the life-fit. | CTX |
| G-06 | P1 | The life is never inferred from history. | Hypotheses from patterns (fuel every week → car; pet shop every month → pet; kindergarten → child) become 1-tap cards and never use up the daily question. **Health, religion etc. are never inferred and never asked about.** | CTX, FE |
| G-07 | P1 | No calendar context. | Romanian calendar + personal rhythms as `expects_event` (Paște, Crăciun, 1 Iunie, 8 Martie, back to school, Black Friday, exam session). | CTX |
| G-08 | P0 | Onboarding step 6 (life profile) is "optional, skip if short on time", yet it's the differentiator. | Onboarding also collects the life: work, who you live with, housing, car / transport, activities, plans for the coming months, what matters / what you'd cut. One rich sentence covers most of it. | CTX |
| G-09 | P0 | No rule for when sources disagree. | Precedence: the user's answer about *this* transaction > learned rule > confirmed fact > hypothesis > population prior. A guess never overrides what the user said. | CTX |

### 3.2 Understanding a transaction and asking the question

| ID | P | Gap in v0.7 | Fix in v0.8 | Owner |
|---|---|---|---|---|
| G-10 | P0 | `signals.detect` is undefined; signals are day-level (overspend at 23:55). | A per-transaction score in the pipeline: `raw = 0.5·stat + 0.2·novelty + 0.3·materiality`, `unexplained = raw·(1−life_fit)·(1−rule_match)`. Hard filters first (small amounts, recurring bills, health → never ask). Decision table auto / inform / ask / ask_later. Day-level overspend stays as a separate signal. | CALC score, CTX fit |
| G-11 | P1 | "It learns" isn't designed. | `pattern_rules`: the same explanation twice → rule at 0.7, three times → 0.9 and auto; "în fiecare vineri…" → a rule right away; a rule stops applying above 2× its amount range; "nu mai întreba de asta" → suppression rule. | CTX |
| G-12 | P0 | A transaction has one amount, so it can't "become 100 lei". | Transaction columns: `effective_amount`, `purpose`, `beneficiary`, `explanation`, `annotation_source`, `annotation_confidence`, `life_fit`, `anomaly_score`, `decision`, `pot_id`. The ledger, baselines and engine all use `effective_amount`. | BE, CALC |
| G-13 | P0 | No "money to recover". | `receivables` + a mock payment request with a status, a reminder at +14 days, mark paid / cancel. | BE |
| G-14 | P0 | No interruption budget. Q19 proposes 2 proactive messages a day, on top of overspend, weekly reflection, preemptive check-ins and cap warnings. The pitch promises ≤ 1 question a day. | Question policy: ≤ 1 *question* a day shared by all sources; pick the one with the biggest goal impact; quiet hours (off in the demo); back off after 2 ignored questions; unanswered for 24h → default "unplanned" with low confidence (editable); volunteered context doesn't count. | CTX |
| G-15 | P0 | Category list, purpose list and merchant mapping undefined (Q8). | A fixed category list, a purpose taxonomy (`essential_living`, `household_care`, `work_tool`, `self_investment`, `identity_joy`, `social_connection`, `planned_event`, `on_behalf_of_others`, `unplanned_discretionary`, `emergency`, `unknown`) and a `merchants` catalogue (Romanian merchants, MCC, typical basket). | CTX lists, BE seed |
| G-16 | P1 | The bank only sees "eMAG 4.500 lei" and can't tell a TV from a fridge. | Optional `items` / `description` on transactions, and the agent asks what it was when that's missing (see §5, Q-A2). | BE, CTX |
| G-17 | P0 | The question isn't linked to its transaction, so the answer run doesn't know what "am luat și pentru colegi" refers to. | `agent_events.ref_transaction_id`, status `pending → asked → answered / expired`; `messages.agent_event_id`; a snapshot block "Open question about transaction #…". | BE, CTX |
| G-18 | P1 | An interpretation can't be undone ("nu, a fost doar pentru mine"). | `annotate_transaction` overwrites; `cancel_receivable`; plan recompute. | CTX, BE |

### 3.3 Engine and the roadmap to the goal

| ID | P | Gap in v0.7 | Fix in v0.8 | Owner |
|---|---|---|---|---|
| G-20 | P0 | No "X% chance" and no "vs last week", though both are in the pitch line. | `engine.forecast_goal`: Monte Carlo (numpy, 10k paths, seeded) over category distributions, income variability, receivables (`p_repay`), pots and shocks → probability, P10/P50/P90, expected reach date, drivers. `goal_forecasts` table + a weekly snapshot. | CALC |
| G-21 | P1 | One `savings_pot` number, no named pots. The pitch ("pușculiță dedicată") and the bank's benefit (money stays in pots) both need them. | `pots` table (the goal pot + named pots), `create_pot`; pot-funded spending is excluded from discretionary. | BE, CALC |
| G-22 | P0 | The engine formula has undefined terms: horizon (to the deadline? to payday?), `available`, essentials floor, what counts as "spent", and how money reaches the goal (only through `transfer_to_savings`?). | Defined in v0.8 §6.7. | CALC |
| G-23 | P0 | A reinterpretation doesn't change the plan. | Receivables count as expected inflow (weighted); the `on_behalf_of_others` part isn't counted as spending; pot-funded spending is excluded. | CALC |
| G-24 | P1 | `plans` has no "why". | `plans.reason` + `trigger_ref`, so the UI can show "de ce s-a schimbat planul" and the agent can explain the diff. | BE, CALC |
| G-25 | P1 | Options and shaping can cut anything. | Never propose cutting essentials, household care or protected categories (`protects` signatures). | CALC |
| G-26 | P1 | A products table exists, but there's no matching rule. "Compare financial products using customer context" is direction #1 on the slide. | Context rule: horizon, liquidity need, income stability → ranked products with a reason; mock catalogue. | CTX, BE seed |

### 3.4 What the AI must know and be able to do

| ID | P | Gap in v0.7 | Fix in v0.8 | Owner |
|---|---|---|---|---|
| G-50 | P0 | The context snapshot (§6.5) has none of the above. | Add: active facts + hypotheses, a household / occupation summary, pattern rules, the open question + its transaction + why it's unusual, the last 14 days of *annotated* transactions, baselines vs this month, receivables, pots, the forecast (now / last week / drivers), the question budget, the last plan-change reason. | CTX builder, BE services |
| G-51 | P0 | No tools for context. | 🆕 `get_transaction`, `annotate_transaction`, `create_receivable`, `request_payment`, `cancel_receivable`, `add_life_fact`, `update_life_fact`, `expire_life_fact`, `confirm_hypothesis`, `create_pattern_rule`, `suppress_questions`, `create_pot`, `update_pot`, `get_goal_forecast`. `update_life_profile` keeps soft notes only. | CTX schemas, BE services |
| G-52 | P0 | No system prompt spec: tone, banned phrases, question rules, "never judge", "explain with a because". | v0.8 §6.9 prompt rules + an eval set of Romanian utterances. | CTX |
| G-53 | P1 | `coach_style = strict` + "RESPECT THE PLAN! 🚨" contradicts "never judgmental". | Styles change the wording (warm / direct), never the judgment. | CTX, BE |

### 3.5 Voice

| ID | P | Gap in v0.7 | Fix in v0.8 | Owner |
|---|---|---|---|---|
| G-40 | P0 | No voice at all, and Claude's API takes text, not audio, so speech needs its own component. | Decided via Q-A1 (§5). `POST /chat {text, input_mode}`; messages carry `speak` + a short `speak_text`; the question is spoken automatically and the mic opens. Chips + a text field stay as the fallback (noisy stage). | FE, BE, CTX |

### 3.6 Data, seed, simulator, demo

| ID | P | Gap in v0.7 | Fix in v0.8 | Owner |
|---|---|---|---|---|
| G-30 | P0 | The personas `maria` and `radu` don't show context. | Personas built for contrast: Matei (main demo), Andrei (sports analyst, TV), Bianca (student, same TV), Ioana (family of 4, Shop&Go). Setup decided via Q-A3. | CALC generator, BE loader |
| G-31 | P0 | One scripted transaction can't be injected on demand. | `POST /sim/transaction {scenario_id}` + scenario scripts per scene. | BE |
| G-32 | P0 | The history generator is unspecified, yet the patterns we demo must be in the history (Mega near the office, Friday team lunch, family baskets). | Generator spec: per-persona config → 3–4 months, seeded, with patterns + calendar. | CALC |
| G-33 | P1 | "10.000 lei până la 31 decembrie" and "vacanță în august, spus din timp" don't fit the real date (28 Oct). | `sim_clock` starts on 2026-06-15 (a Monday). | BE |
| G-34 | P0 | No deterministic fallback for when the LLM or the internet fails on stage. | Quick-reply chips map to deterministic actions for the demo transaction; a templated question. | CTX |

### 3.7 Frontend contract (Flutter)

| ID | P | Gap in v0.7 | Fix in v0.8 | Owner |
|---|---|---|---|---|
| G-60 | P0 | §3 says "any framework", but the app is Flutter (Riverpod, chopper, drift, FCM), and the base project has email/password login screens. | The contract is written for Flutter; packages for WS / voice / auth are noted. | FE |
| G-61 | P0 | Missing endpoints. | `GET /transactions/{id}`, `PATCH /transactions/{id}` (user fixes purpose / own share), `GET /receivables`, `POST /receivables/{id}/request-payment · mark-paid · cancel`, `GET/POST/PATCH/DELETE /life-facts`, `POST /life-facts/{id}/confirm · reject`, `GET /pots`, `GET /forecast`, `GET /products`, `POST /sim/transaction`, `PATCH /me`. | BE |
| G-62 | P0 | Missing WS events. | `transaction.annotated`, `receivable.updated`, `forecast.updated`, `pot.updated`, `fact.hypothesis`. | BE |
| G-63 | P0 | `/state` lacks the probability, its delta, receivables, pots and the pending question; the Transaction shape lacks the annotation. | v0.8 §9.3 shapes. | BE |
| G-64 | P1 | WebSocket events only arrive while the app is open. | Demo: WS only (app in the foreground). FCM is already in the app, so it's an optional later step. | FE, BE |

### 3.8 Platform

| ID | P | Gap in v0.7 | Fix in v0.8 | Owner |
|---|---|---|---|---|
| G-70 | P0 | Keycloak + Flutter: PKCE needs `flutter_appauth` and a redirect scheme. On an Android emulator Keycloak is reached at `10.0.2.2`, so the token's `iss` differs from `localhost` and JWT validation fails unless `KC_HOSTNAME` is one address reachable from both. That's costly in 24h. | ✅ Keycloak stays and is hosted with one public HTTPS hostname, which removes the mismatch (D36). A `savings-dev` client lets scripts log in without a browser. | BE, FE |
| G-71 | P1 | The doc says `backend/app/`, but the repo has `api/`. | Use `api/app/`. 🆕 **2026-10-29: reversed.** bomboe created `backend/` as the app folder (commit 6214a5d), and every doc now says `backend/`. | BE |
| G-72 | P1 | Phone ↔ laptop networking at the venue. | ✅ Solved by hosting the backend (D38). | BE |
| G-73 | P1 | A sync Anthropic client inside async FastAPI background tasks blocks the event loop. | `AsyncAnthropic`, or run the agent in a threadpool. | BE, CTX |
| G-74 | P2 | Env vars aren't listed. | Listed in v0.8 §3. | BE |

### 3.9 Claude API details (Sonnet 5.5, D16)

| ID | P | Gap in v0.7 | Fix in v0.8 | Owner |
|---|---|---|---|---|
| G-80 | P0 | The loop breaks on any `stop_reason != "tool_use"` and returns the text, so a `refusal` or `max_tokens` would be shown as the reply. | Handle `end_turn` / `tool_use` / `max_tokens` / `refusal` explicitly, with a fallback template; optionally the server-side refusal fallback (`fallbacks: "default"`). | CTX |
| G-81 | P1 | Effort isn't set, and Sonnet 5.5 defaults to `high`, which is slow for voice. | `output_config={"effort": "low"}` on chat / proactive runs (measure). Never send `temperature` (a non-default value → 400). Forced `tool_choice` `any`/`tool` → 400, so use `auto`. | CTX |
| G-82 | P1 | Tool inputs are validated only by Pydantic, after the fact. | `strict: true` on tool definitions (+ `additionalProperties: false`); Pydantic stays as the domain check. | CTX |
| G-83 | P2 | No prompt-caching layout. | Frozen rules first, then the snapshot, then messages; deterministic tool order. Today's date sits in the snapshot, not in the frozen rules. | CTX |
| G-84 | — | Within one run, append `resp.content` unchanged, thinking blocks included (v0.7 already does this; keep it). On Sonnet 5.5, text between tool calls arrives as thinking blocks, so the final `text` blocks are the reply, which settles Q16. | — | CTX |

### 3.10 Contradictions inside v0.7

| ID | Where | Problem → fix |
|---|---|---|
| G-90 | D12, §13 | "Team of 3" → we are 4; §13 rewritten. |
| G-91 | §9.3 Notification example | "RESPECT THE PLAN! 🚨" violates the no-judgment rule → rewritten. |
| G-92 | Q19 | "2 proactive messages a day" vs the pitch's ≤ 1 question a day → D25. |
| G-93 | D10 | "No confirmations" vs a payment request that messages other people → Q-A4. |
| G-94 | §4.2 `agent_events UNIQUE(user_id, type, date)` | Blocks two transaction-question candidates on the same day → `(user_id, type, ref_transaction_id)` for transaction events. |
| G-95 | `slips` | Day-level reasons vs per-transaction annotations → slips stay for day-level overspend only. |
| G-96 | F9 `PATCH /life-profile/{key}` | Facts have ids → `/life-facts/{id}`. |

---

## 4. Interfaces between the teams

The AI team's code lives **inside bomboe's FastAPI app** as modules (`context/`, `engine/`, `agent/`), with the same DB, called in-process (no separate AI service, no context bundle over HTTP). To work in parallel, a fixed set of function signatures is the contract, and each side mocks the other until it's ready. Full list: architecture doc v0.8 §15.

## 5. Questions

| ID | For | Question | Status | In the architecture doc |
|---|---|---|---|---|
| Q-A1 | David G. | Voice: on-device STT/TTS, cloud STT/TTS through the backend, or text + chips only? | ✅ **On the device** (2026-10-28) | D29, F15, Q37 |
| Q-A2 | David G. | Item detail: synthetic items + ask when missing, ask only, or always items? | ✅ **Optional items + ask when missing** | D32, Q38 |
| Q-A3 | David G. | Demo personas: seeded + 1 live onboarding, all live, or all seeded? | ✅ **4 seeded personas + 1 live onboarding** | D30, 16.1, Q39 |
| Q-A4 | David G. | Which actions need a user tap (vs D10)? | ✅ **Only outward actions** (sending a payment request) | D31, Q40 |
| Q-B1 | bomboe | Keep Keycloak (fixed `KC_HOSTNAME`, `flutter_appauth`) or a demo login? | ✅ **Keycloak stays**: hosted with one public hostname (2026-10-28) | D36, 5.1, Q30 |
| Q-B2 | bomboe + danutu | Auto-save: does the planned saving move to the goal pot on payday automatically? | ✅ **Yes** | D37, 6.7, Q31 |
| Q-B3 | bomboe | Where does the backend run during the demo (laptop on a hotspot, tunnel, cloud VM)? | ✅ **Hosted** (probably); provider / URL still to pick | D38, Q22 |
| Q-B4 | bomboe | Review the 🟡 decisions D23–D28 and D33–D35 | ✅ **Approved** | §2 |
| Q-F1 | David V. | Home screen: probability as the big number, `saved / target` as the bar? | David V. decides: his work is separate for now (D39) | Q32 |
| Q-F2 | David V. | Open the mic automatically after the spoken question? | David V. decides (D39) | Q36 |
| Q-F3 | David V. | Persona switcher in the app for the Andrei vs Bianca scene? | David V. decides (D39); the backend still offers `GET /sim/personas` | 9.2 |

All P0–P2 gaps above are now covered in the architecture doc **v0.8** (search for 🆕).
