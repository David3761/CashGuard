# TASKS: the short list for assigning (API only)

> Full detail of every task (files, functions, steps, tests, "done when"): [`backend/docs/work-breakdown.md`](backend/docs/work-breakdown.md).
> How we work on each task: [`backend/docs/how-we-work.md`](backend/docs/how-we-work.md). The frontend is David V.'s and separate (arch D39).
> ✅ Assigned on 2026-10-28. Each person's tasks in detail, split into steps: [`Bomboe.md`](Bomboe.md), [`Danutu.md`](Danutu.md), [`DGAdavid1.md`](DGAdavid1.md).
>
> **P0** = needed for the demo (Scenes A + B) · **P1** = clearly better pitch · **P2** = cut first.
> **Hours** = rough, with Claude Code, including tests and review. **Suggested** = the owner proposed in the architecture doc §13, rebalanced so each person has ~13.5h of P0.

## Foundations

| ID | Task | P | h | Depends on | Suggested | Assigned |
|---|---|---|---|---|---|---|
| F1 | Repo skeleton, tooling, config, clock, error envelope | P0 | 0.5 | — | David G. | **David G.** |
| F2 | Shared domain types & enums (`app/domain/`), money helpers, test builders | P0 | 1 | F1 | David G. | **David G.** |
| F3 | Test infrastructure: DB / API / auth / WS fixtures | P0 | 1 | F1, B1, B2 | bomboe | **bomboe** |

## Backend platform

| ID | Task | P | h | Depends on | Suggested | Assigned |
|---|---|---|---|---|---|---|
| B1 | docker-compose, env, Keycloak realm (3 clients, 5 personas), cron container | P0 | 0.75 | F1 | bomboe | **bomboe** |
| B2 | DB models for every table + constraints + indexes | P0 | 1.5 | F1, F2 | bomboe | **bomboe** |
| B3 | CRUD services (user-scoped, state machines) | P0 | 1.5 | B2 | bomboe | **bomboe** |
| B4 | `load_user_context` read model (the AI's view of the user) | P0 | 0.75 | B3 | bomboe | **bomboe** |
| B5 | Auth: JWT/JWKS validation, `current_user`, internal role, WS token | P0 | 1 | F1, B3 | bomboe | **bomboe** |
| B6a | REST core: /me, /state, /messages, /notifications, /plan, /transactions, /transfers undo | P0 | 1 | B3, B4, B5 | bomboe | **bomboe** |
| B6b | REST context: /forecast, /receivables (+ request-payment), /pots, /life-facts, /products | P1 (request-payment P0) | 1 | B3, C4, C9 | bomboe | **bomboe** |
| B7 | WebSocket manager + event builders + push-after-commit | P0 | 0.75 | B5 | bomboe | **bomboe** |
| B8 | Ingestion + processing pipeline (locks, retries, evaluate → apply → recompute → question) | P0 | 1.5 | B3, B7 | bomboe | **bomboe** |
| B9 | `POST /chat` + background agent run + busy lock + fallback | P0 | 0.75 | B3, B7 | bomboe | **bomboe** |
| B10 | Simulator: next-day, jump, reset, transaction (scenarios), personas | P0 | 1 | B8, B12 | bomboe | **bomboe** |
| B11 | Day jobs + internal endpoints + cron schedule | P1 | 1 | B8, E11, C7 | bomboe | **bomboe** |
| B12 | Seed loader (personas, facts, rules, history, merchants, products) | P0 | 0.75 | B2, B3, E12, D1, C4 | danutu | **bomboe** |
| B13 | Notifications service + RO/EN templates | P1 | 0.5 | B3, C1, A5 | bomboe | **bomboe** |
| B14 | Hosting & deploy (HTTPS, Keycloak hostname, smoke script) | P0 | 1 | B1 | bomboe | **bomboe** |
| B15 | Audit logging (agent_runs, tool_calls) + privacy | P1 | 0.5 | B3, A6 | bomboe | **bomboe** |

## Engine & calculations

| ID | Task | P | h | Depends on | Suggested | Assigned |
|---|---|---|---|---|---|---|
| E1 | Calendar utilities (paydays, month ends, ranges) | P0 | 0.5 | F2 | danutu | **danutu** |
| E2 | Budget engine core: daily budget, weights, pins, buffer, floor, feasibility | P0 | 1.5 | E1, F2 | danutu | **danutu** |
| E3 | `apply_transaction` + ledger + re-annotation deltas | P0 | 1 | F2, B3 | danutu | **danutu** |
| E4 | `recompute_plan` + versions + reason | P0 | 0.5 | E2, B3 | danutu | **danutu** |
| E5 | `simulate_plan` + solve mode | P1 | 1 | E2, E8 | danutu | **danutu** |
| E6 | Baselines + OECD household scale + essentials floor | P0 | 1 | F2, C1 | danutu | **danutu** |
| E7 | Anomaly features (stat, novelty, materiality) | P0 | 0.5 | E6 | danutu | **danutu** |
| E8 | Monte Carlo goal forecast + weekly snapshots | P0 | 2 | E1, E6, F2 | danutu | **danutu** |
| E9 | Drivers & options (never cut protected/essential) | P1 | 1 | E8 | danutu | **danutu** |
| E10 | Pots, expected receivables, payday auto-save, transfers | P0 | 1 | E2, B3 | danutu | **danutu** |
| E11 | Day-level signals (warning, overspend, caps, goal completed) | P1 | 0.75 | E2, B3 | danutu | **danutu** |
| E12 | Persona data generator (4 months of history with the demo patterns) | P0 | 2 | F2, C1, C2 | danutu | **danutu** |
| E13 | Calibrate the demo numbers (78 → 71 → 77, last week 72) | P1 | 0.75 | E8, E12, B12, C6, A3 | danutu | **danutu** |

## Context layer (personalisation)

| ID | Task | P | h | Depends on | Suggested | Assigned |
|---|---|---|---|---|---|---|
| C1 | Fixed lists, RO/EN labels, number formats, merchants / priors / products / calendar data | P0 | 1 | F2 | danutu | **David G.** |
| C2 | Merchant normalisation (raw bank text → merchant + category) | P0 | 0.5 | C1 | danutu | **David G.** |
| C4 | Signature library + `signatures_for_fact` (library + Claude's, validated) | P0 | 1.5 | F2, C1 | David G. | **David G.** |
| C5 | `life_fit` + the "because" explanation | P0 | 1.5 | C4, F2 | David G. | **David G.** |
| C6 | `evaluate_transaction` (hard filters, score, decision, question hint) | P0 | 1 | C2, C5, E6, E7 | David G. | **David G.** |
| C7 | Question policy (≤ 1/day, priority, quiet hours, back-off, suppression) | P0 | 1 | C6, B3 | danutu | **David G.** |
| C8 | Learning rules ("every Friday team lunch → stop asking") | P1 | 1 | F2, B3 | David G. | **David G.** |
| C9 | Propagation on a fact change (re-evaluate, re-plan) | P1 | 1 | C4, C6, E6, E3, E4, E8 | David G. | **David G.** |
| C10 | Hypotheses inferred from history (1-tap cards; never sensitive) | P2 | 0.75 | C4, B3 | David G. | **David G.** |
| C11 | Calendar expected events (Orthodox Easter algorithm, 1 Iunie, school…) | P2 | 0.5 | C4, C1 | David G. | **David G.** |
| C12 | Product ranking by context (mock catalogue) | P2 | 0.5 | C1 | David G. | **David G.** |

## Agent & LLM

| ID | Task | P | h | Depends on | Suggested | Assigned |
|---|---|---|---|---|---|---|
| A1 | Claude client wrapper (Sonnet 5.5 settings) + `FakeLLM` for tests | P0 | 0.5 | F1 | David G. | **David G.** |
| A2 | Tool schemas (strict), registry, `tools_for` | P0 | 1 | F2 | David G. | **David G.** |
| A3 | Tool executor + every tool handler (annotate, receivables, facts, pots…) | P0 | 2 | A2, B3, E3, E4, E8, E10, C4 | David G. | **David G.** |
| A4 | Snapshot builder (what Claude knows about the user) | P0 | 1 | B4, F2, C1 | David G. | **David G.** |
| A5 | Prompts RO/EN + banned-phrase checker + templates | P0 | 0.75 | C1 | David G. | **David G.** |
| A6 | Agent loop (stop reasons, parallel tools, fallbacks, speak text) | P0 | 1 | A1–A5 | David G. | **David G.** |
| A7 | Proactive runs: the spoken question after an anomaly | P0 | 1 | A6, C7, B3 | David G. | **David G.** |
| A8 | Live onboarding (fresh account) | P2 | 0.5 | A6, A3 | David G. | **David G.** |
| A9 | Deterministic fallbacks when the LLM is down (demo safety) | P1 | 0.75 | A3, A5 | David G. | **David G.** |
| A10 | LLM eval set (60–100 RO/EN utterances) + runner | P1 | 1 | A6, A3, D1 | David G. | **David G.** |
| A11 | Language detection + `speak_text` for TTS | P1 | 0.5 | A5 | David G. | **David G.** |

## Data, demo & quality

| ID | Task | P | h | Depends on | Suggested | Assigned |
|---|---|---|---|---|---|---|
| D1 | Persona life facts + Matei's seeded Friday rule | P0 | 0.75 | F2, C4 | David G. | **David G.** |
| D2 | Scenario files for the demo scenes | P0 | 0.5 | E12, C1 | danutu | **David G.** |
| D3 | Acceptance suite (the 15 cases of arch 16.3) | P1 (#1–#7 P0) | 1 | C6, A3, E8, B12 | David G. | **David G.** |
| D4 | Demo client script (runs and asserts the scenes against the API) | P0 | 0.75 | B5, B7, B9, B10 | bomboe | **David G.** |
| D5 | Demo runbook + rehearsal | P1 | 0.5 | D4 | everyone | **David G.** |
| D6 | Security & privacy review | P1 | 0.5 | most | David G. | **David G.** |

## Load per person (✅ assigned 2026-10-28 by David G.)

Backend platform → **bomboe**; engine & calculations → **danutu**; context layer, agent & LLM, data/demo/quality → **David G.**; foundations as suggested (F1, F2 → David G.; F3 → bomboe).
Detailed per-person files: [`Bomboe.md`](Bomboe.md) · [`Danutu.md`](Danutu.md) · [`DGAdavid1.md`](DGAdavid1.md).

| Person | P0 hours | All hours |
|---|---|---|
| bomboe | ~13.75 | ~16.25 |
| danutu | ~10.25 | ~13.75 |
| David G. | ~18 | ~26.5 |

Moving C1, C2, C7 and D2 (≈ 3 h of P0) from David G. to danutu would even it out (~15 / ~13.25). Not done; David G. decides.

⚠️ **Time check (2026-10-28 21:15):** if the hackathon ends around 10:00 tomorrow with a feature freeze around 05:00 (arch §13 hour 19), there are about **8 build hours** left. P0 alone is ~13.5h per person, so **even P0 is over capacity**. Options: work fast on P0 only and accept fewer review rounds; cut more (B14 hosting, E8 → a simpler forecast, C7 → a plain "1 per day" rule); or confirm a later end time.
