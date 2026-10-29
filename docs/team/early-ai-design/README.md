> **Superseded (kept for history).** These are David G.'s first AI design notes from 2026-10-28, written before the team settled on bomboe's architecture. The source of truth is [`backend/docs/savings-coach-backend-architecture.md`](../../../backend/docs/savings-coach-backend-architecture.md); the live decision log is [`../DGAREADME1.md`](../DGAREADME1.md). `DGAREADME1-2026-10-28.md` here is that log's first version.

# CashGuard — Documentation

CashGuard is a voice-first financial companion for young people (VibeHack, Raiffeisen Bank track
"AI for Scaling & Growth"). It understands the **life behind each transaction**, asks at most one
question a day when something is out of pattern, and keeps a live, personalised roadmap to the
user's savings goal.

## Documents

| # | Document | What's inside |
|---|---|---|
| 01 | [Challenge & pitch](01-challenge-and-pitch.md) | hackathon brief, problem, differentiator, pitch |
| 02 | [System architecture](02-system-architecture.md) | components, owners, end-to-end flows, voice, `ai/` layout |
| 03 | [Life Context Model](03-life-context-model.md) | **core**: facts, spending signatures, life-fit, context-adjusted baselines, examples |
| 04 | [Transaction understanding](04-transaction-understanding.md) | normalisation, anomaly score, decision table, question policy, learned rules |
| 05 | [Conversation & actions](05-conversation-and-actions.md) | question phrasing, answer intents, action catalogue, agent tools |
| 06 | [Goal engine](06-goal-engine.md) | cash-flow model, Monte Carlo probability, roadmap, re-planning, options |
| 07 | [AI API contract](07-ai-api-contract.md) | endpoints and JSON schemas between AI service, backend, mobile |
| 08 | [Personas & demo](08-personas-and-demo.md) | synthetic personas, data generator, mock products, demo script |
| 09 | [LLM integration](09-llm-integration.md) | Claude usage, structured outputs, caching, prompts, eval set |

Decision log and discussion notes: [`../DGAREADME1.md`](../DGAREADME1.md).

## Reading order by role

- **Frontend (David V.)**: 01 → 02 → 07 (response shapes you render) → 08 §5 (demo script).
- **Backend (bomboe)**: 01 → 02 → 07 (you call these endpoints and apply the actions) → 05 §5 (actions).
- **AI (David G., danutu)**: everything, starting with 03.
