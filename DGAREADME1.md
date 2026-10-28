# DGAREADME1 — Discussion log, decisions & important notes (David G.)

> Running log of what we discussed and decided for the AI side of CashGuard.
> Detailed design lives in [`docs/`](docs/README.md). Update this file after every discussion.
>
> Status legend: ✅ **Agreed** (comes from the team/brief) · 🟡 **Proposed** (from the design pass,
> needs team OK) · ❓ **Open** (someone must decide)

---

## 1. Context

- **Event:** VibeHack (nexxt × Raiffeisen Bank), track **"AI for Scaling & Growth"**, 2026-10-28.
- **Challenge (from the slide):** build an AI agent that actively helps an individual or business
  navigate financial decisions and services. Directions: compare products using customer context,
  support budgeting/saving decisions, guide onboarding. Must show an agent that **uses relevant
  information and tools to complete a meaningful task, beyond a search interface or fixed decision
  tree**. Use fictional profiles, synthetic spending, mock product catalogues. → `docs/01`
- **Repo state when we started:** `main` had only `README.md` (UTF-16 encoded, shows garbled in some
  tools — convert to UTF-8 at some point) and an empty `mobile/`. Branch **`api-ai`** created from
  `main` at `9a3f518` for the AI work.

## 2. Team & ownership ✅

| Person | Area | Folder |
|---|---|---|
| David V. | Frontend | `mobile/` |
| bomboe | Backend API | `backend/` |
| David G. (me) + danutu | AI API + calculations | `ai/` (to create) |

🟡 **P-15 — split inside the AI team:** David G. → Life Context engine + LLM (docs 03, 05, 09);
danutu → calculations (anomaly scoring in 04, goal engine in 06, data generator in 08).
We both own the API contract (07).

## 3. The product idea ✅ (summary of our pitch notes)

- Don't pitch "young people waste money" (judgmental). Pitch: *young people want to reach goals but
  have no real picture of their money; apps see transactions, not the life behind them.*
- Differentiator = **context, not budgeting**. The agent asks **one** voice question, only on anomalies,
  classifies the answer and acts (colleagues → 100 lei + 400 to recover; vacation → pot; moved → replan;
  "am cedat" → recalc without reproach). It learns recurring patterns and stops asking.
- Live goal probability: "81% șanse … față de 72% săptămâna trecută".
- Rules: ≤ 1 question/day, only anomalies, never judging.
- For Raiffeisen: money stays in pots at the bank; young customers don't leave for Revolut.
- Honest risk: Revolut already has budgets & pots → pitch opens with the **context moment**.
- 60-second demo: Mega 500 lei → voice question → "am luat și pentru colegi" → 100 lei + debt + bar ↑.
- ⚠️ Verify the Deloitte 2026 and Revolut numbers (and their sources) before they go on a slide.

## 4. David G.'s core requirement ✅ — extreme personalisation

> "I want it super personalized and the context super precise — it must perfectly correlate the
> activities and the actual life to the respective purchases."

What this means for the design (all detailed in `docs/03`):

- **No purchase is good or bad in itself.** Meaning = f(purchase, person, moment).
  TV → work tool for a sports analyst, treat for a student. Big Shop&Go basket → normal for a family of 4.
- **The roadmap to the goal must change whenever the correlations / life change** (household grows,
  rent changes, new job, vacation planned).

## 5. Design decisions

| ID | Decision | Status | Where |
|---|---|---|---|
| P-01 | AI = separate **Python 3.12 + FastAPI + Pydantic + numpy** service in `ai/` | 🟡 | 02 §6 |
| P-02 | AI service is **stateless**: backend sends a **context bundle** per request, stores everything, executes actions | 🟡 (agree with bomboe) | 07 §1 |
| P-03 | **"LLM understands & talks, code computes."** The LLM never does money math, never executes actions | 🟡 | 02 §4, 09 §1 |
| P-04 | Purchases get a **purpose** (taxonomy) + **life-fit score**, never "good/bad" | 🟡 | 03 §1, §10 |
| P-05 | **Life Profile = facts** (source, confidence, status, validity window) + **spending signatures** per fact (`explains`, `scales_baseline`, `expects_event`, `suppresses_question`) | 🟡 | 03 §3–4 |
| P-06 | Signatures from a **curated library** (~40 common facts) + **LLM-generated once per free-text fact** (same schema) | 🟡 | 03 §4 |
| P-07 | Life-fit = best match between the transaction and any signature × fact confidence × **need saturation** (replacement cycle), plus personal precedent and pots | 🟡 | 03 §5 |
| P-08 | Context precedence: user's answer > learned rule > confirmed fact > inferred hypothesis > population prior; inferred never overrides explicit | 🟡 | 03 §5 |
| P-09 | Household scaling with the **OECD-modified equivalence scale** (1 / 0.5 / 0.3; family of 2+2 = 2.1) + Bayesian blend of personal history and context prior (k = 5); **instant rescale** on household change | 🟡 | 03 §6 |
| P-10 | Baselines use **effective amounts** (own share, pot-funded excluded, fraud excluded) so one shared purchase doesn't break "normal" | 🟡 | 03 §6.4 |
| P-11 | Inferred facts stay **hypotheses** until a 1-tap confirmation; sensitive categories (health etc.) are **never inferred and never asked about** | 🟡 | 03 §2, §7 |
| P-12 | Anomaly: `raw = 0.5·stat + 0.2·novelty + 0.3·materiality`; `unexplained = raw·(1−life_fit)·(1−rule_match)`; ask if ≥ 0.55 (thresholds tuned on personas) | 🟡 | 04 §3–5 |
| P-13 | Question policy: ≤ 1/day hard cap, pick the question that changes the plan most, quiet hours, back-off, max 1 follow-up (prefer tap card), unanswered → default after 24h, volunteered context free | 🟡 | 04 §6 |
| P-14 | Learning: same pattern explained 2× → rule (0.7), 3× → auto (0.9); explicit "în fiecare vineri" → rule immediately; rule breaks if amount > 2× range | 🟡 | 04 §8 |
| P-16 | Answers → **list** of interpretations (multi-intent), each multi-dimensional (intent, purpose, beneficiary, persistence, planned, confidence) + entities | 🟡 | 05 §3–4 |
| P-17 | Anything that **moves money or contacts other people** (payment request, pot creation, card freeze) needs an explicit user tap | 🟡 | 05 §5 |
| P-18 | Own share when not stated → **estimated from the personal baseline** + tap card "~100 lei?" | 🟡 | 05 §6 |
| P-19 | Goal probability by **Monte Carlo** (10k sims, numpy, seeded); outputs P10/P50/P90, drivers, options; weekly snapshots for "vs last week" | 🟡 | 06 |
| P-20 | When probability drops: up to 3 options with their own probability; never cut essentials / household / protected categories; user chooses | 🟡 | 06 §6 |
| P-21 | LLM = **Claude `claude-opus-5-5`** via official `anthropic` Python SDK; `effort: low` on real-time calls; structured outputs via `messages.parse` + Pydantic; prompt caching on the user context slice | 🟡 (needs API key) | 09 |
| P-22 | Deterministic **fallbacks everywhere**: template question, quick-reply chips, text input | 🟡 | 05 §2, 08 §5 |
| P-23 | **Demo clock** `as_of = 2026-06-15` so "31 decembrie" and "august" make sense | 🟡 | 08 §1 |
| P-24 | Transparency screen **"Ce știe CashGuard despre mine"** — all facts visible/editable; every annotation carries a "because" | 🟡 (frontend) | 02 §3, 03 §5 |
| P-25 | 5 fictional personas: Matei (main demo), Andrei vs Bianca (same TV), Ioana (family of 4), Radu (freelancer) | 🟡 | 08 §2 |

## 6. Open questions ❓

1. How long is the hackathon, when is the pitch, what are the judging criteria / pitch length?
2. Mobile stack (React Native/Expo? Flutter? web?) — affects the voice option. → David V.
3. Backend stack + DB, and agreement on the context-bundle contract (P-02). → bomboe
4. Which API keys/credits do we have: Anthropic (Claude), speech-to-text, text-to-speech (ro-RO)?
5. Voice option A (device STT/TTS) or B (cloud)? (02 §5)
6. Does the bank want the payment request to look like a specific Raiffeisen feature, or a generic mock?
7. UI language: Romanian only? (Docs assume Romanian user-facing text.)
8. Final demo numbers (probabilities 72% → 78% → 71% → 77%) — tune after the simulator works.

## 7. Next steps (AI team)

1. Agree P-02 / doc 07 with bomboe and the response shapes with David V. (30 min meeting).
2. Create `ai/` skeleton (FastAPI + Pydantic schemas from doc 07).
3. danutu: data generator + baselines + anomaly score + Monte Carlo on persona Matei.
4. David G.: signature library (start with the 5 personas' facts) + `interpret_answer` + `phrase_question` + eval set.
5. End-to-end Scene A with fixtures (no backend needed), then plug into the backend.
6. Then Scene B (Andrei vs Bianca), then C/D.

## 8. Changelog

- **2026-10-28** — Branch `api-ai` created. Read the challenge slide and the pitch notes. Wrote the
  full design (docs 01–09) and this log. All design decisions are 🟡 until the team reviews them.
