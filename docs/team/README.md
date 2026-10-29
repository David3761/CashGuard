# How the team worked

These are the process documents from the hackathon build, kept as they were written between 28 and 29 October 2026. For what the product is and how to run it, see the [root README](../../README.md). For the design, see the [architecture doc](../../backend/docs/savings-coach-backend-architecture.md).

## Who did what

| Who | Area | Their task file |
|---|---|---|
| **David G.** (DGAdavid1) | Foundations (F1, F2), the Life Context layer (C*), the Claude agent (A*), data, demo and quality (D*) | [`DGAdavid1.md`](DGAdavid1.md) |
| **Alexandru Bomboe** (bomboe) | The backend platform: DB, services, auth, REST, WebSocket, pipeline, simulator, cron, deploy (B*, F3) | [`Bomboe.md`](Bomboe.md) |
| **Crăciun Dan Nicolae** (danutu) | The engine: budget, ledger, baselines, anomaly, the Monte Carlo forecast, persona data (E*) | [`Danutu.md`](Danutu.md) |
| **David Vlaicu** | The Flutter app (`mobile/`) | see [`mobile/README.md`](../../mobile/README.md) |

## The documents

| File | What it is |
|---|---|
| [`TASKS.md`](TASKS.md) | Every backend task (F, B, E, C, A, D) with priority, estimate, dependencies and owner |
| [`DGAREADME1.md`](DGAREADME1.md) | The decision log: every decision (D1…) and open question (Q1…), with who agreed and when, plus a dated changelog |
| [`HANDOFFS.md`](HANDOFFS.md) | Work done on a teammate's behalf (team rule D42: build it yourself and log it, don't wait). Each entry has a merge instruction |
| [`ORCHESTRATION.md`](ORCHESTRATION.md) | How David G.'s tasks ran as parallel Claude agents: one agent per task, a boss session gating every step with an independent review and `make check` |
| [`Bomboe-merge-notes.md`](Bomboe-merge-notes.md) | bomboe's merge notes for the platform branch: what he built, what he assumed, and what differs from the spec |
| [`engine-merge-notes.md`](engine-merge-notes.md) | danutu's merge notes for the engine branch (formerly `backend/merged_notes.md`) |

For each task there are also step plans and reports in [`backend/docs/plans/`](../../backend/docs/plans/) and [`backend/docs/reports/`](../../backend/docs/reports/), the working method in [`backend/docs/how-we-work.md`](../../backend/docs/how-we-work.md), and the detailed task specs in [`backend/docs/work-breakdown.md`](../../backend/docs/work-breakdown.md).
