# CashGuard

A voice-first money companion for young people that understands the life behind each transaction (VibeHack 2026, nexxt × Raiffeisen Bank).

## Documentation

| Doc | What's inside |
|---|---|
| [`backend/docs/savings-coach-backend-architecture.md`](backend/docs/savings-coach-backend-architecture.md) | **The architecture (source of truth):** data, flows, Life Context layer, AI, API contract |
| [`backend/docs/architecture-gap-review.md`](backend/docs/architecture-gap-review.md) | What v0.7 was missing and why each v0.8 addition exists |
| [`TASKS.md`](TASKS.md) | Every API task, who owns it |
| [`Bomboe.md`](Bomboe.md) · [`Danutu.md`](Danutu.md) · [`DGAdavid1.md`](DGAdavid1.md) | Each person's tasks, split into steps |
| [`backend/docs/work-breakdown.md`](backend/docs/work-breakdown.md) | The tasks in detail + conventions + the test checklist |
| [`backend/docs/how-we-work.md`](backend/docs/how-we-work.md) | How we implement, test and review each step |
| [`DGAREADME1.md`](DGAREADME1.md) | Decision log |
| [`HANDOFFS.md`](HANDOFFS.md) | Work done on someone else's behalf, with merge instructions |
| [`ORCHESTRATION.md`](ORCHESTRATION.md) | How David G.'s tasks run as parallel agents + a boss (plans, gates, merges) |
| [`backend/README.md`](backend/README.md) | How to set up, run and test the backend |
| [`backend/docs/reports/`](backend/docs/reports/) | Step reports and reviews per task |

In this README, "arch §x" means a section of the architecture doc.

## 1. The hackathon challenge

**VibeHack** (nexxt × Raiffeisen Bank), track **"AI for Scaling & Growth"** — captured from the
stage slide on 2026-10-28.

- **The challenge:** Build an AI agent that actively helps an individual or business navigate
  financial decisions and services.
- **Possible directions:**
  - Compare financial products using customer context
  - Support budgeting or saving decisions
  - Guide customers through onboarding
- **What to demonstrate:** An agent that uses relevant information and tools to complete a
  meaningful task, **beyond a basic search interface or fixed decision tree**.
- **Data for the demo:** fictional customer profiles, synthetic spending histories, or mock
  financial product catalogues.

How CashGuard maps to it:

| Slide requirement              | CashGuard                                                                      |
| ------------------------------ | ------------------------------------------------------------------------------ |
| Actively helps                 | the agent starts the conversation, only when something is out of pattern       |
| Uses relevant information      | Life Context Model: who you are, who you live with, what you do (arch §5.3)    |
| Uses tools                     | creates pots, receivables, payment requests, rules, re-plans the goal (arch §6.6) |
| Beyond a decision tree         | open voice answers understood by an LLM; probabilistic goal engine; learning   |
| Budgeting / saving decisions   | live goal probability + roadmap (arch §6.7)                                    |
| Compare products using context | pot vs term deposit for a goal in N months (mock catalogue)                    |
| Onboarding                     | conversational onboarding that builds the life profile (arch F8)                |
| Fictional data                 | 4 seeded personas + 1 fresh account, 4 months of history (arch §16.1)          |

## 2. The problem (from our pitch notes)

Do **not** pitch "young people spend on irrelevant things" — it sounds like judgment and puts us in
conflict with the exact user we want to win.

Data points from our notes (⚠️ verify the exact sources and numbers before putting them on a slide):

- Deloitte 2026 study: 55% of Gen Z in Romania feel financially insecure; 46% live paycheck to
  paycheck; more than half postponed important life decisions because of money.
- For the bank: young people's money doesn't stay there — Revolut passed 4.8 million retail
  customers in Romania; almost one in two people in Bucharest uses it.

**Final problem statement:** young people want to reach their goals but don't have a real picture of
their money. Apps see transactions, not the life behind them.

## 3. The differentiator: context, not budgeting

Every app says "ai cheltuit 500 lei la Mega". None knows **why**. CashGuard asks **one** question,
by voice, only when something is out of pattern, then classifies the answer and acts:

| User says                                     | Agent does                                                                                                       |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| "Am luat și pentru colegi"                    | your real expense becomes 100 lei; 400 lei to recover; reminds you and can send the payment request              |
| "Merg în vacanță în august" (said in advance) | creates a dedicated pot and splits the cost over the remaining months — the vacation is planned, not a deviation |
| "M-am mutat, chiria e mai mare"               | permanent change → recalculates the whole plan                                                                   |
| "Am cedat, mi-am luat adidași"                | no reproach, just recalculates the route to the goal                                                             |

And it **learns**: if every Friday is lunch with the team, it stops asking. The route updates live:
"Ai 81% șanse să strângi 10.000 lei până la 31 decembrie, față de 72% săptămâna trecută."

**Our extra layer (David G.'s requirement): extreme personalisation.** The same purchase means
different things for different people — a TV is a work tool for a sports analyst; a big Shop&Go
basket is normal for a family of 4. The roadmap changes whenever the life changes. See arch §5.3.

## 4. Rules so it doesn't become annoying

At most **one question per day**, only on anomalies, never in a judging tone. A companion that
interrogates you about every coffee gets uninstalled in 3 days. (Details: arch §5.3.6.)

## 5. Why it's worth it

- Matches the slide's direction exactly: budgeting and saving decisions based on customer context.
- A real agent: detects anomalies, understands voice, keeps memory, recalculates and acts.
- For Raiffeisen: money that stays in pots at the bank, and young customers who don't leave for Revolut.

**Honest risk:** Revolut already has budgets and pots. That's why the pitch must **open with the
context moment**, not with budgeting.

## 6. Demo (60 seconds)

The 500 lei transaction at Mega appears → the agent asks by voice → you answer "am luat și pentru
colegi" → on screen the expense becomes 100 lei, the debt to recover appears, and the goal bar goes up.
Full script and backup scenes: arch §16.2.
