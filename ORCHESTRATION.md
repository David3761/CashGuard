# ORCHESTRATION: one agent per task, one boss

> Decided by David G. (DGAdavid1) on 2026-10-29 (DGAREADME1 **D44**). This is how David G.'s tasks in [`DGAdavid1.md`](DGAdavid1.md) are built: in parallel by separate AI agents, coordinated by an orchestrator. The quality bar doesn't change: [`backend/docs/how-we-work.md`](backend/docs/how-we-work.md) (tests first, every test category, review after every step).

## 1. Roles

| Role | Who | Does |
|---|---|---|
| **Owner** | David G. | approves every agent's **plan** before it writes any code; can stop, redirect or comment on anything at any time |
| **Boss** (orchestrator) | the main Claude session | starts the agents, brings their plans to David G., gates every step (independent review + `make check`), merges, applies the shared docs, sequences dependencies between agents, reports to and explains for David G. |
| **Task agent** | one Claude agent per task (F1, F2, C1, …) | plans its task, then implements it step by step in its own worktree; stops after every step for the boss |
| **Reviewer** | a fresh Claude agent per step | reviews the step's diff with no anchoring on the task agent's conclusions; reports findings only |

## 2. The flow of one task

```
1. PLAN      agent (plan mode = read-only; the only file it writes is its plan)
             → backend/docs/plans/<TASK>.md in its worktree → returns it to the boss
2. APPROVE   boss summarises the plan for David G. → David G. approves / changes it
3. STEP n    agent: test analysis → tests first (red, shown) → implement (green) → make check
             → self-review (how-we-work §5) → step report in backend/docs/reports/<TASK>.md → STOP
4. GATE      boss: independent reviewer on the step diff + re-runs make check in the worktree
             → findings back to the agent → fixes + post-review report → boss re-checks
5. MERGE     agent commits "[<TASK>] step n: …" on its branch → boss merges into dga-final
             → boss updates the shared docs → boss tells the agents that were waiting for it
6. repeat 3–5 until the task is done → boss reports the finished task to David G.
```

- **Blocked:** if a step needs something another agent is still building, the agent stops and reports `BLOCKED: needs <what> from <TASK>`. The boss resumes it once that work is merged; the agent then rebases its branch on `dga-final`.
- **Something only a teammate owns** (bomboe, danutu, David V.): do it and log it (D42). The agent builds the minimum and **proposes** a `HANDOFFS.md` entry in its report; the boss writes it.
- **The arch doc looks wrong or incomplete:** the agent stops and raises it (how-we-work §2 rule). It never silently implements something different.

## 3. Git

- `dga-final` is the integration branch for David G.'s work. Nothing is pushed unless David G. says so.
- Every task agent works in its own worktree: **`.worktrees/<task>/`** on branch **`dga-task/<task>-<slug>`** (not `dga/…`: a branch named `dga` already exists), created from `dga-final`. `.worktrees/` is excluded locally (`.git/info/exclude`).
- One commit per reviewed step: `[F2] step 1: enums + money`. Only the boss merges (`git merge --no-ff`).

## 4. Who may edit what (so parallel branches merge cleanly)

| Files | Edited by |
|---|---|
| The task's own code, tests, `backend/docs/plans/<TASK>.md`, `backend/docs/reports/<TASK>.md` | that task agent |
| `DGAdavid1.md`, `DGAREADME1.md`, `HANDOFFS.md`, `ORCHESTRATION.md`, `README.md`, `TASKS.md`, `Bomboe.md`, `Danutu.md`, everything in `backend/docs/` except plans/reports | **boss only** (agents put proposed changes in their reports) |
| `backend/pyproject.toml`, `uv.lock`, `requirements.txt` | only via a dependency change agreed with the boss (all §0.1 deps are already in) |
| `backend/app/main.py` | F1's agent (wiring); others propose |
| `backend/tests/conftest.py` | boss / F1 (bomboe's F3 later); others propose |
| Empty package markers (`__init__.py`) | anyone, but **always empty** (identical files merge without conflict) |

## 5. The roster

| Task | Agent | Worktree / branch | Needs (from) | Status |
|---|---|---|---|---|
| F1 (F1.2–F1.5) | f1 | `.worktrees/f1` · `dga-task/f1-skeleton` | — | F1.2, F1.3 ✅ merged · F1.4 review fixes |
| F2 | f2 | `.worktrees/f2` · `dga-task/f2-domain` | — | 1a, 1b, 2 ✅ merged · building step 3 |
| C1 | c1 | `.worktrees/c1` · `dga-task/c1-lists` | — | C1.1, C1.2 ✅ merged · C1.3 recalibration (D50/D51) |
| A1 | a1 | `.worktrees/a1` · `dga-task/a1-llm` | — | steps 1–2 ✅ merged · step 3 review fixes |
| A5 | a5 | `.worktrees/a5` · `dga-task/a5-prompts` | — | A5.1 ✅ merged · building A5.2 |

**Next waves** (an agent starts as soon as its inputs are merged): S0, C2, C4, A2 (after F2) → D1, C5, A4 → C6, A3 → C7, A6 → A7, D2 → D4 → ★ checkpoint (Scene A) → the P1 / P2 tasks. Dependencies: [`DGAdavid1.md`](DGAdavid1.md) §1–§2 and [`backend/docs/work-breakdown.md`](backend/docs/work-breakdown.md) §1.
