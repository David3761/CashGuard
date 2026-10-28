# DGAREADME1: discussion log, decisions & important notes (David G.)

> A running log of what we discussed and decided. Update it after every discussion.
> **Source of truth for the architecture:** [`backend/docs/savings-coach-backend-architecture.md`](backend/docs/savings-coach-backend-architecture.md) (bomboe's doc, now v0.8 with the AI team's additions marked 🆕).
> Why each addition was made: [`backend/docs/architecture-gap-review.md`](backend/docs/architecture-gap-review.md).
>
> Status legend: ✅ **Agreed** · 🟡 **Proposed** (needs the owner's OK) · ❓ **Open**

---

## 1. Context

- **Event:** VibeHack (nexxt × Raiffeisen Bank), track **"AI for Scaling & Growth"**, started 2026-10-28, 24 hours.
- **Challenge (slide):** build an AI agent that actively helps an individual or business navigate financial decisions and services. Directions: compare financial products using customer context · support budgeting or saving decisions · guide customers through onboarding. **What to demonstrate:** an agent that uses relevant information and tools to complete a meaningful task, *beyond a basic search interface or fixed decision tree*. **Data:** fictional customer profiles, synthetic spending histories, mock product catalogues.
- **Repo:** `backend/` = the Python app, with the docs in `backend/docs/` · `mobile/` = the Flutter base project. bomboe **created** `backend/` in 6214a5d (a copy of the 4 docs + an empty `requirements.txt`); the old `api/` copy is still tracked and goes away with the commit that lands F1 (it's deleted in the working tree). Branches: `backend/` exists on `api-development` (team API work) and `dga-final` (David G., local, not pushed yet); **`main` still has only `api/`**. Also `engine-development` (danutu) and `api-ai` (obsolete).
  - ✅ 2026-10-28: the **`api-ai` branch is old** (an earlier separate-AI-service design). We stick with bomboe's architecture. Only ideas from `api-ai` were reused, adapted to bomboe's design.
  - ✅ `README.md` was UTF-16; it was converted to UTF-8 in 3a2ed0e.

## 2. Team & ownership ✅

| Person | Area | Owns (details: arch doc §13) |
|---|---|---|
| David V. | Frontend | Flutter app in `mobile/`: home, feed, chat, voice, profile screen, slides |
| bomboe | Backend platform | DB, CRUD, auth, REST + WebSocket, pipeline plumbing, simulator, cron, seed loader |
| David G. (me) | AI: context layer + agent | `context/` (life facts → signatures → life-fit, questions, learning), `agent/` (prompts, tools, snapshot), eval set |
| danutu | AI: calculations | `engine/` (daily budget, baselines, anomaly maths, Monte Carlo goal forecast), persona data generator |

✅ The AI team's code lives **inside bomboe's FastAPI app** as modules, same DB, called in-process (arch D34, §15). No separate AI service.

✅ **David V.'s work is separate from ours for now, and he decides everything app-side** (arch D39). The architecture doc only fixes what the backend provides (§9); UI ideas in it are suggestions. We test our side with a scripted demo client, not the app.

## 3. The product idea ✅ (from our pitch notes)

- Don't pitch "young people waste money on irrelevant things": it sounds like judgment and fights the user we want to win. Pitch: *young people want to reach their goals but have no real picture of their money; apps see transactions, not the life behind them.*
- Data for the pitch (⚠️ verify the sources before they go on a slide): Deloitte 2026, 55% of Romanian Gen Z feel financially insecure, 46% live paycheck to paycheck, more than half postponed big life decisions because of money. Revolut passed 4.8M retail customers in Romania; almost one in two Bucharest residents uses it.
- **Differentiator = context, not budgeting.** One question, by voice, only when something is out of pattern; the answer is classified and acted on:
  - "Am luat și pentru colegi" → the real expense becomes 100 lei, 400 lei to recover, reminder + payment request.
  - "Merg în vacanță în august" (said in advance) → a dedicated pot, split over the remaining months. Planned, not a deviation.
  - "M-am mutat, chiria e mai mare" → permanent change → full replan.
  - "Am cedat, mi-am luat adidași" → no reproach, just recalculate the route.
  - It learns: team lunch every Friday → it stops asking. Live: "Ai 81% șanse să strângi 10.000 lei până la 31 decembrie, față de 72% săptămâna trecută."
- **Rules:** at most one question a day, only on anomalies, never in a judging tone.
- **For Raiffeisen:** money that stays in pots at the bank; young customers who don't leave for Revolut.
- **Honest risk:** Revolut already has budgets and pots, so the pitch must **open with the context moment**.
- **60-second demo:** Mega 500 lei → the agent asks by voice → "am luat și pentru colegi" → 100 lei, the debt to recover appears, the goal bar goes up.

## 4. David G.'s core requirement ✅: extreme personalisation

> "I want it super personalized and the context super precise: it must perfectly correlate the activities and the actual life to the respective purchases."

- **No purchase is good or bad in itself.** Meaning = f(purchase, person, moment). A TV is a work tool for a sports analyst and a question for a student; a big Shop&Go basket is normal for a family of 4.
- **The roadmap must change whenever the life or the correlations change** (household grows, rent changes, new job, vacation planned).
- How the design delivers it (arch §5.3): structured **life facts** → **spending signatures** (what each fact predicts) → a **life-fit** score per transaction with a "because" → **household-adjusted baselines** (OECD scale, family of 4 = 2.1) → anomaly only if large *for this person* and unexplained → ≤ 1 question a day → answer → tools → **instant re-plan + new probability**. Every life change propagates (arch §5.3.9).

## 5. Review of bomboe's architecture (2026-10-28)

**Verdict:** v0.7 was a solid platform (Postgres, queue, Claude tool calling, WebSocket, simulator, cron, error handling) but **not complete end-to-end** for our pitch. It described a *daily-budget coach* (reacting at 23:55 to a day over budget), not a *context companion* (reacting to one transaction against the person's life). The 60-second demo couldn't run on it. Missing: the whole life-context layer, per-transaction anomaly + question, effective amounts, receivables, pots, goal probability, voice, learning, the question budget, the AI's snapshot + tools for all of this, endpoints / WS events for the app, personas, team interfaces, a 4-person split. Full list (G-01…G-96): `backend/docs/architecture-gap-review.md`.

**What we did:** folded every gap into the architecture doc as **v0.8**, marking each addition 🆕 so bomboe can review it. New sections: 4.4–4.5 (tables, fixed lists), 5.3 (Life Context layer), 6.8 (Claude API settings), 6.9 (prompt rules), F10–F16 (flows), 15 (team function contracts), 16 (personas, demo script, acceptance tests, data files).

## 6. Decisions

| ID | Decision | Status | Arch doc |
|---|---|---|---|
| — | bomboe's architecture is the baseline; `api-ai` is obsolete | ✅ team, 2026-10-28 | — |
| D25 | At most **1 question a day**, shared by every source; only anomalies; never judging | ✅ pitch rule | §2, 5.3.6 |
| D29 | **Voice is text on the backend** (`speak` hints); we recommend on-device STT/TTS in the app, but the app side is David V.'s call (D39) | ✅ David G., 2026-10-28 | §2, F15 |
| D30 | **4 seeded personas** (Matei, Andrei, Bianca, Ioana) for the contrast scenes **+ 1 fresh account** (Alex) for live onboarding | ✅ David G., 2026-10-28 | §2, 16.1 |
| D31 | **Only outward actions need a tap** (sending a payment request); everything else stays no-confirm (bomboe's D10), with undo | ✅ David G., 2026-10-28 | §2, F11 |
| D32 | **Item detail:** synthetic transactions *may* carry items (like an e-receipt); if missing at a multi-category shop (eMAG…), the one question asks what it was | ✅ David G., 2026-10-28 | §2, 5.3.4 |
| D23 | Life Context layer: `life_facts` + `spending_signatures` + `life_fit` + purpose + "because" | ✅ bomboe approved, 2026-10-28 | §2, 5.3 |
| D24 | Every transaction is evaluated in the pipeline (not only at close-day) | ✅ bomboe | §2, F3 |
| D26 | `effective_amount` everywhere (ledger, baselines, engine, forecast) | ✅ bomboe | §2 |
| D27 | Goal probability via Monte Carlo + weekly snapshots ("vs last week") | ✅ bomboe (the maths: danutu to confirm 6.7) | §2, 6.7 |
| D28 | Receivables and named pots are tables | ✅ bomboe | §2, 4.4 |
| D33 | Never judgmental; `coach_style` = `warm` / `direct` (wording only); banned phrases checked in code | ✅ bomboe | §2, 6.9 |
| D34 | The AI team's code lives in the same FastAPI app; in-process function contracts | ✅ bomboe | §2, §15 |
| D35 | Demo clock starts 2026-06-15 (Monday) so "31 decembrie" and "vacanță în august" make sense | ✅ bomboe | §2 |
| D36 | **Keycloak stays.** Hosted with one public HTTPS hostname (`KC_HOSTNAME` = backend's `KEYCLOAK_ISSUER`), so the `iss` mismatch is gone; a dev-only `savings-dev` client lets scripts log in | ✅ bomboe, 2026-10-28 | §2, 5.1 |
| D37 | **Auto-save on payday:** processing a salary moves the planned saving to the goal pot (`transfers.kind = auto_save`, undoable, quiet notification) | ✅ bomboe | §2, 6.7 |
| D38 | **The backend is hosted** (probably; provider / URL to pick) | ✅ bomboe | §2, Q22 |
| D39 | **Frontend = David V.'s call**, separate from us for now | ✅ team | §2, §9 |
| — | Claude: keep bomboe's `claude-sonnet-5-5` (D16); `effort: low` on chat/proactive runs; `AsyncAnthropic`; handle `refusal` / `max_tokens`; `strict: true` tools; no `temperature`; `tool_choice: auto` only | 🟡 David G. | 6.3, 6.8 |
| — | Signatures for free-text facts are written by Claude inside `add_life_fact` (no extra LLM call); the curated library wins | 🟡 David G. | 5.3.3, Q35 |
| D40 🆕 | **The app folder is `backend/`** (bomboe created it in 6214a5d, replacing `api/`); every doc path updated | ✅ David G. + bomboe's commit, 2026-10-29 | §5 |
| D41 🆕 | **Packaging:** uv + `pyproject.toml` + `uv.lock` are the source of truth; `requirements.txt` is generated (`make requirements`) for the Docker image, and `make check` fails on drift. The app starts via the factory `uvicorn app.main:create_app --factory --workers 1` | ✅ David G. · 🟡 bomboe to confirm ([HANDOFFS](HANDOFFS.md) H-2) | work-breakdown 0.1 |
| D42 🆕 | **Cross-team rule:** when one of us needs something another owns, we build it ourselves and log it in [`HANDOFFS.md`](HANDOFFS.md) with a merge instruction (no skipping, no waiting) | ✅ team, 2026-10-29 | — |
| D44 🆕 | **Orchestrated parallel agents:** one AI agent per David G. task, coordinated by the main session (the boss): every agent plans first and waits for David G.'s approval; after that, every step is gated by an independent review + `make check` before it's merged into `dga-final`. Process: [`ORCHESTRATION.md`](ORCHESTRATION.md) | ✅ David G., 2026-10-29 | how-we-work |
| D45 🆕 | **Refusal fallback** (arch 6.8): setting `ANTHROPIC_REFUSAL_FALLBACK`, **off by default**. On Sonnet 5.5 it only rescues `cyber`/`frontier_llm` declines, our template already handles refusals, and a rejected beta header would fail every call. Turned on in the hosted `.env` only after A1's live test proves our key accepts the beta | ✅ David G., 2026-10-29 | 6.8 |
| D46 🆕 | **D21 amended: the tool list is fixed per run.** `tools_for` runs once at the start of a run, not every iteration: on Sonnet 5.5, changing tools mid-run while thinking blocks are replayed returns HTTP 400 for API accounts created on/after 2026-08-31. Onboarding still works (`set_goal` takes the motivation; a 2nd `set_goal` gets `goal_already_active`); `update_goal` is offered from the next message | ✅ David G., 2026-10-29 · bomboe to be told (D21 was his) | D21, 6.3, 6.7 |
| D47 🆕 | **Merchant ids are text slugs** (`mega_image`, `emag`): `merchants.id` is the slug and `transactions.merchant_id` / rule matches use it | ✅ David G., 2026-10-29 · bomboe's B2 key ([HANDOFFS](HANDOFFS.md)) | 4.4 |
| D48 🆕 | **First-wave plans approved** with their proposed defaults (`.worktrees/<task>/backend/docs/plans/`). **F1:** `tzdata` + `time.time_ns` ban; shared test fixtures in `tests/conftest.py`; the cron secret stays in `Settings`. **A1:** cache the conversation tail; FakeLLM rejects requests the real API would 400 on; `get_llm()`/`set_llm()`; live tests incl. one tool round trip. **F2:** 0–1 scores `float`, money `Decimal`; >2 decimals rounded half-up, \|x\| ≥ 10^10 rejected; 9 extra enums; inferred shapes for the undefined fact types (danutu reviews); money in JSON as a plain number (31.2). **C1:** one shared `fold()` in `app/i18n/text.py`; formats `-30,40 lei` / `100 lei` / `15 iunie 2026`; 53 merchants; Romanian product names. **A5:** every "iar" / "de ce" is flagged, even neutral; inflections matched; `irosi…` added; one English system prompt with RO + EN examples; templates in `app/agent/templates.py` | ✅ David G., 2026-10-29 | — |
| D43 🆕 | F1 is split into 5 reviewable steps (F1.1 tooling + factory, F1.2 settings, F1.3 clock, F1.4 error envelope, F1.5 logging) + DOC-0 (doc paths); reports in [`backend/docs/reports/F1.md`](backend/docs/reports/F1.md) | ✅ David G., 2026-10-29 | how-we-work §2 |

## 7. Open questions ❓

| ID | For | Question | Proposal |
|---|---|---|---|
| Q22 | bomboe | Which hosting provider / public URLs for the backend and Keycloak? | — (hosting itself is decided, D38) |
| Q33 | bomboe | Payment request: mock only (status + notification)? | Mock |
| Q35 | David G. | Signatures for free-text facts inside `add_life_fact`, or a separate LLM call? | Inside `add_life_fact` |
| — | danutu | Confirm the engine definitions and the Monte Carlo design (arch 6.7) | — |

| — | all | Pitch length, judging criteria, pitch time slot? | ask the organisers |
| — | all | Anthropic API key / credits available? | needed by hour 1 |
| — | David G. | Verify the Deloitte 2026 and Revolut numbers and their sources before the slides | — |
| — | bomboe | Confirm D41 (uv + generated `requirements.txt`, the `--factory` start) and review the work done for him: [`HANDOFFS.md`](HANDOFFS.md) H-1 (test-DB compose), H-2 | merge instructions are in each entry |
| — | David G. | Tell bomboe and danutu when F1 lands (they're blocked on it). **F2 step 1a (the enums for B2's CHECKs) is on `dga-final` (d184687)**: `app/domain/enums.py`; generate the CHECK lists from it, never copy them by hand | — |
| — | bomboe | Heads-up from A5/D46/D47: B13 notification texts must avoid the banned words (also "iar" as "and", "din nou"/"try again", "de ce"); B9's exception fallback uses `fallback_reply("llm_down", lang)`; D21 is amended (D46); merchant ids are slugs (D47); the Docker image needs no system tzdata (the `tzdata` package is in `requirements.txt`) | tell him at the next sync |
| — | all | Which branch is the integration branch? how-we-work §9 says "rebase on `main`", but the team works on `api-development` and `main` has no `backend/` yet | `api-development` until the first merge to `main` |

Answered on 2026-10-28: Q30 → Keycloak stays (D36) · Q31 → auto-save yes (D37) · Q22 → hosted (D38) · the 🟡 decisions → approved. The frontend questions (home screen, auto mic, persona switcher) are **David V.'s to decide** (D39); they don't block the backend or the AI.

## 7b. How we work & the task list ✅ (2026-10-28)

- **Way of working** (David G.): implement in **small steps** (one concern, ≤ ~150 lines). Each step goes plan → test analysis over every category → tests first (red) → implement (green) → `make check` → self-review → step report → human review → a post-review report (what went wrong, why, the fix, how we prevent it). Details: [`backend/docs/how-we-work.md`](backend/docs/how-we-work.md).
- **Every task in detail:** [`backend/docs/work-breakdown.md`](backend/docs/work-breakdown.md) (60 tasks: files, functions, steps, edge cases, every test, "done when").
- **Short list:** [`TASKS.md`](TASKS.md). ✅ **Assigned by David G.:** backend platform (B1–B15, incl. the seed loader B12) → **bomboe**; engine & calculations (E1–E13) → **danutu**; context layer (C1–C12), agent & LLM (A1–A11), data/demo/quality (D1–D6) → **David G.**; foundations as suggested (F1, F2 → David G.; F3 → bomboe). Per-person detailed files, each task split into reviewable steps with the tests per step and "who needs what from whom, by when": [`Bomboe.md`](Bomboe.md), [`Danutu.md`](Danutu.md), [`DGAdavid1.md`](DGAdavid1.md).
- ⚠️ Load after the assignment: P0 ≈ 13.75 h (bomboe) / 10.25 h (danutu) / 18 h (David G.). Moving C1, C2, C7, D2 to danutu would even it out (open, David G.'s call).
- 🟡 Technical defaults in work-breakdown §0 (uv, async SQLAlchemy, `create_all` instead of migrations, a pure core + thin DB shell for engine/context, Decimal money, real Postgres in tests, `FakeLLM` in tests and real Claude only with `-m live`). Platform choices need bomboe's OK.
- ⚠️ **Time risk:** at 21:15, P0 is ~13.5h per person; with a freeze around 05:00 there are ~8 build hours. Needs a decision: confirm the end time, cut more, or accept fewer review rounds.

## 8. Next steps (AI team)

1. ✅ v0.8 reviewed by bomboe (decisions approved, Q30 / Q31 / Q22 answered).
2. Hour 0–1: commit stubs for our §15 functions (`evaluate_transaction`, `pick_question`, `build_snapshot`, `recompute_plan`, `forecast_goal`, `auto_save`, …) returning fixtures, so bomboe can integrate.
2b. With bomboe: the scripted demo client (`backend/scripts/demo_client.py`, arch §14) so we can run Scenes A–E without the app.
3. **danutu:** persona generator (Matei first), baselines, budget engine definitions incl. payday auto-save (6.7), anomaly features, Monte Carlo forecast with the demo numbers 78% → 71% → 77% (last week 72%).
4. **David G.:** `data/merchants.json`, the fixed lists (4.5), the signature library, `evaluate_transaction` passing acceptance tests 16.3 #1 and #3–#7, the snapshot builder, the tools (6.6), the prompts (6.9), then the eval set (16.4).
5. Checkpoint at hour 11–12: Scene A end-to-end.
6. Then Scenes B → D → C → E.

## 9. Changelog

- **2026-10-28**: Read the challenge slide, the pitch notes and bomboe's architecture v0.7. The team confirmed bomboe's doc as the baseline (`api-ai` is old). Reviewed v0.7 for end-to-end completeness → `api/docs/architecture-gap-review.md`. David G. decided voice (on the device), item detail (optional items + ask), demo users (4 seeded + 1 live) and confirmations (only outward actions). Upgraded the architecture doc to **v0.8**, all additions marked 🆕. Started this log on `main`.
- **2026-10-28 (later)**: bomboe's answers: Keycloak stays because we host it (D36); auto-save on payday: yes (D37); the backend will be hosted (D38); the 🟡 decisions are OK. David V.'s work is separate for now and he decides everything app-side (D39). The architecture doc, the gap review and this log are updated. The backend/AI checkpoint is now verified with a scripted demo client instead of the app.
- **2026-10-28 21:15**: Agreed the way of working (small steps, tests first, reviews with post-review reports). Wrote `api/docs/work-breakdown.md` (every API task in detail), `TASKS.md` (the short list with suggested owners, waiting for assignment) and `api/docs/how-we-work.md`. Flagged that P0 doesn't fit the remaining time.
- **2026-10-28 (later)**: David G. assigned the tasks (platform → bomboe, engine → danutu, context/agent/data/demo/quality → David G.; foundations as suggested). Wrote `Bomboe.md`, `Danutu.md`, `DGAdavid1.md` and updated `TASKS.md` and `work-breakdown.md`. The per-person files are now the working copies.
- **2026-10-29**: bomboe created `backend/` as the app folder (6214a5d, replacing `api/`); David G. agreed, and every doc path now says `backend/` (D40; the changelog lines above keep the old paths as history). Packaging decided: uv + generated `requirements.txt` (D41). New team rule: do it yourself and log it in `HANDOFFS.md` (D42). F1 split into steps (D43); **F1.1 done and approved** (tooling, `create_app()`, `GET /api/health`, test-DB compose); report: `backend/docs/reports/F1.md`.
- **2026-10-29 (later)**: DOC-0 approved. David G. switched to **parallel agents** (D44, [`ORCHESTRATION.md`](ORCHESTRATION.md)): first wave F1 (F1.2–F1.5), F2, C1, A1, A5, each in its own worktree. The baseline (F1.1 + DOC-0 + the shared hypothesis profile, HANDOFFS H-4) is committed on `dga-final`.
- **2026-10-29 (later)**: The five first-wave plans are approved (D48), with D45 (refusal fallback off), D46 (D21 amended: tools fixed per run) and D47 (merchant ids are slugs). `tzdata`, `types-jsonschema` and the `time.time_ns` ban were added centrally on `dga-final` (f5f8c05) so that two branches never edit `uv.lock`. F2's step 1 is split into 1a/1b (≤ ~150 lines). One shared `fold()` comes from C1.1, and A5.1 waits for it.
- **2026-10-29 (later)**: **F2 step 1a merged** (d184687): the 10 first enums + the household-scaled and never-asked sets, values checked twice against arch 4.4/4.5. The review's test-strength findings (doc-parsed golden lists, deterministic set order, cross-enum value overlaps) follow as 1a-fix. C1.2+ unblocked.
