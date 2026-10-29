# How we work (API)

> Agreed 2026-10-28 (David G.). Applies to every API task in [`TASKS.md`](../../docs/team/TASKS.md), whether it's done by a person alone or with Claude Code.
> Detailed task specs: [`work-breakdown.md`](work-breakdown.md). Architecture (the *what*): [`savings-coach-backend-architecture.md`](savings-coach-backend-architecture.md).

## 1. The idea

**Small steps, each one tested, explained and reviewed before the next.** A task from `docs/team/TASKS.md` is split into steps. A **step** is one concern and about ≤ 150 changed lines of code (tests not counted), small enough that a human can review it in 5–10 minutes. Nothing moves on until the step is green and reviewed.

## 2. The loop for every step

| # | Stage | What happens | Output |
|---|---|---|---|
| 1 | **Plan** | What this step does and why, which files it touches, whether it changes a contract (arch §15, a schema, an event, an endpoint) | 3–10 lines |
| 2 | **Test analysis** | Go through **every** category of the test table (work-breakdown §0.4): happy, boundaries, invalid, errors, security, concurrency, idempotency, time, money, language, personalisation, invariants, performance, regression. List each case: *case → expected → why it matters*. Say explicitly which categories don't apply and why | a table |
| 3 | **Tests first (red)** | Write the tests. Run them. Confirm they fail **for the right reason** (not an import error) | test file + red run |
| 4 | **Implement (green)** | The minimum code that makes them pass, following the conventions in work-breakdown §0.3 | code |
| 5 | **Run** | The step's tests → the module's suite → `make check` (ruff, mypy, all non-live tests) | results |
| 6 | **Self-review** | Go through the checklist in §5 below, and fix what it finds before showing anything | findings |
| 7 | **Explain** | The step report (§3): what changed, why, how it's tested, the real test output, known limits | report |
| 8 | **Human review** | The owner (and, for a contract change, the people who depend on it) reads the diff + report and comments | comments |
| 9 | **Fix & post-review report** | Fix every comment, re-run everything, and for each problem explain *what went wrong, why, how it was fixed, and how we prevent it next time* (§4). Usually the prevention is a new test | report |
| 10 | **Close** | Commit (only when the owner says so), tick the step in the person's file, add a line to the `docs/team/DGAREADME1.md` changelog when a decision changed, update the arch doc when a contract changed | commit + docs |

**Rules**
- A test that never failed proves nothing: step 3 must show red before step 4.
- Never weaken a test to make it pass. If a test is wrong, say so in the report and explain why.
- "It works on my machine" isn't green: green means `make check` passed, with the output pasted.
- If a step grows beyond ~150 lines or a second concern appears, split it.
- If something in the arch doc turns out wrong or missing, **stop and raise it**. Don't silently implement something different.

## 3. Step report template

```markdown
### <Task ID>.<step n>: <title>

**What & why.** …

**Contract impact.** none | <what changed, who is affected, arch doc section updated>

**Test analysis.**
| # | Category | Case | Expected | Why it matters |
|---|---|---|---|---|
| 1 | boundary | unexplained = 0.55 exactly | ask | threshold is inclusive (arch 5.3.4) |
| … | | | | |
Not applicable: concurrency (pure function), …

**Red run.** `uv run pytest tests/unit/test_x.py` → 7 failed (expected: function missing)

**Implementation.** files + the main idea in 2–5 lines.

**Green run.** `make check` → ruff ok · mypy ok · 142 passed, 0 failed (paste the summary line)

**Self-review findings.** what the checklist caught and how it was fixed (or "none").

**Known limits / follow-ups.** …
```

## 4. Post-review report template

```markdown
### Review of <Task ID>.<step n>

| # | Problem found | Why it happened | Fix | Prevention |
|---|---|---|---|---|
| 1 | receivable was 333.34 for 500 / 3 | rounded each share, then multiplied | others = total − own share | property test: own + others == total |

**Re-run.** `make check` → … passed.
```

## 5. Self-review checklist (stage 6, and for human reviewers)

**Correctness**
- [ ] Does it do exactly what the arch doc / work breakdown says? Every number, threshold and enum value matches.
- [ ] Every branch has a test; every test category was considered (§2 stage 2).
- [ ] Error codes are the documented ones; error messages are clear enough for Claude or a user to act on.

**Personalisation (our core requirement)**
- [ ] Nothing labels a purchase good or bad; the meaning comes from the person's facts.
- [ ] The user's own answer always wins over guesses (arch 5.3.2 precedence).
- [ ] No sensitive inference (health, religion…); health spending is never asked about.

**Money & time**
- [ ] `Decimal` everywhere outside Monte Carlo internals; splits add up exactly; no negative effective amounts.
- [ ] No `datetime.now()`; the shell uses `clock`, cores receive `today`; Bucharest time zone for day boundaries.

**Security & privacy**
- [ ] Every query is scoped by `user_id`; another user's ids give `not_found`.
- [ ] `user_id` is never a tool input; write tools are refused in proactive runs.
- [ ] Text from transactions/users is treated as data in prompts; no IBANs/card numbers in snapshots; no secrets in code, logs or git.

**Code quality**
- [ ] Pure core / thin shell respected; no hidden global state.
- [ ] Types complete (mypy strict passes on domain/engine/context); names say what things are.
- [ ] User-facing text only from `app/i18n` (RO + EN) or Claude, and never judgmental (banned-phrase checker).
- [ ] Matches the surrounding code's style; no dead code, no stray prints.

**Performance**
- [ ] The budgets in the arch doc are asserted (forecast < 100 ms, snapshot builder, query counts).

**Docs**
- [ ] The person's task file is updated; the arch doc is updated if a contract changed (marked 🆕, with a changelog line in `docs/team/DGAREADME1.md`).

## 6. Definition of done (a whole task)

1. Every step went through the loop, and the post-review report shows no open problem.
2. Every test listed for the task in the work breakdown exists and passes, plus any found during the analysis.
3. `make check` is green on `main` after merging.
4. The functions in arch §15 for this task match their documented signatures (the stubs other people used still work).
5. The task is ticked in the person's file with a link to the step reports.

## 7. Test strategy

| Layer | Folder | Marker | Needs | Typical speed |
|---|---|---|---|---|
| Unit (pure cores) | `tests/unit/` | — | nothing | ms |
| Database | `tests/db/` | `db` | Postgres (`make db-up`) | 10–100 ms |
| API | `tests/api/` | `api` | Postgres | 10–100 ms |
| WebSocket | `tests/ws/` | `ws` | Postgres | 10–100 ms |
| Acceptance (demo numbers) | `tests/acceptance/` | — | the committed persona files | < 1 s |
| Live LLM eval | `tests/eval/` | `live` | Claude credentials (`ANTHROPIC_API_KEY` or Bedrock), **costs money** | seconds |
| End-to-end | `scripts/smoke_local.sh` (stack + Scene A's transaction); `tests/unit/agent/test_scene_a.py` (the scene, scripted LLM) | — | the running stack / nothing | seconds |

- **Determinism:** time via `FixedClock`; every random generator is seeded (never Python's `hash()`); no `sleep` in tests. A flaky test is a bug, fixed at once.
- **The LLM in tests:** every test uses `FakeLLM` with a scripted response. Real Claude runs only with `-m live`, deliberately.
- **Golden files** (`tests/golden/`): a reviewed expected output (e.g. the snapshot text). A golden diff must be read by a human before it's accepted. Never regenerate blindly.
- **Property tests** (hypothesis) for invariants: sums, ranges, monotonicity, "never raises".
- **Naming:** `test_<unit>_<behaviour>_<condition>`, e.g. `test_split_share_sums_to_total_for_three_people`.
- **Coverage targets:** `app/domain`, `app/engine`, `app/context` ≥ 90% of lines; the rest ≥ 75%. Coverage is a hint, not the goal: the categories list is.

## 8. Commands

```bash
cd backend
uv sync                         # install
make db-up                      # Postgres for tests (docker compose up -d db-test)
make test                       # unit + db + api + ws (everything except live)
make check                      # ruff + mypy + make test
uv run pytest tests/unit/test_money.py -q        # one file
uv run pytest -m live tests/eval                 # real Claude: only on purpose
uv run python -m app.db.seed --reset             # reseed the dev DB
scripts/smoke_local.sh                           # the whole stack + Scene A's transaction
```

## 9. Git

- **One branch per task:** `api/<task-id>-<slug>` (e.g. `api/c6-evaluate`). Rebase on `main` often; merge after the task's review.
- **Small commits, one per step:** `[C6] evaluate: hard filters + tests`. Never commit `.env` or keys.
- With Claude Code: Claude **never commits or pushes unless the owner says so**.
- **Contract changes** (anything in arch §15, the DB schema, an event, an endpoint shape): announce them to the people affected, update the arch doc (🆕 + a `DGAREADME1.md` changelog line) and update the stubs others use, all in the same change.

## 10. Working with Claude Code (for each teammate)

Start every session with:

> Read `backend/docs/how-we-work.md`, `backend/docs/work-breakdown.md` (task <ID>), the architecture doc sections it references, and `<YourName>.md`. We're doing task <ID>, step 1. Follow the loop: plan → test analysis → tests (red) → implement (green) → `make check` → self-review → step report. Stop after the report and wait for my review.

Then review each step report, comment, and let Claude produce the post-review report before moving on.
