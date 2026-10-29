# Contributing to CashGuard

Thanks for helping. The way we plan, test and review every change is described in
[`backend/docs/how-we-work.md`](backend/docs/how-we-work.md); this page is the short version.
The architecture (the source of truth for contracts) is
[`backend/docs/savings-coach-backend-architecture.md`](backend/docs/savings-coach-backend-architecture.md).

## Setup

You need [uv](https://docs.astral.sh/uv/), Docker (with Compose) and, for the app,
[Flutter](https://docs.flutter.dev/get-started/install) stable (3.47+, Dart 3.13+).

**Backend** (FastAPI, Python 3.12; uv installs the right Python):

```bash
cd backend
cp .env.example .env     # dev values; never commit .env
make install             # uv sync --locked: the app + dev tools, exactly as locked
make db-up               # throwaway Postgres for the tests (docker compose service db-test)
make check               # everything that must be green: lock, ruff, mypy, pytest
```

`make help` lists every target (`make dev`, `make test`, `make fmt`, …). Tests that call the
real Claude API are marked `live` and never run by default (`make test-all` runs them, and costs
money).

**Mobile** (Flutter):

```bash
cd mobile
flutter pub get
flutter analyze
flutter test
```

**Optional: pre-commit hooks** (ruff, gitleaks, whitespace) from the repo root:

```bash
uvx pre-commit install
```

## The rules

1. **`make check` must be green** before anything is reviewed or merged, with the summary line
   pasted in the PR. "It works on my machine" isn't green. CI runs the same checks on every PR to
   `main`.
2. **Tests first.** Write the tests, show them failing for the right reason, then implement.
   Never weaken a test to make it pass.
3. **Small steps.** One concern per step, about 150 changed lines of code at most (tests not
   counted), each with a step report ([how-we-work §3](backend/docs/how-we-work.md)).
4. **No secrets.** Never commit `.env`, keys or real customer data. Report security problems
   privately (see [`SECURITY.md`](SECURITY.md)).
5. **Contract changes** (an endpoint, the DB schema, an event, an agent tool) update the arch doc
   and get a line in the [`DGAREADME1.md`](docs/team/DGAREADME1.md) decision log in the same change.

## Branches and commits

- One branch per task, e.g. `api/c6-evaluate`; rebase on `main` often.
- One small commit per step, prefixed with the task ID from [`TASKS.md`](docs/team/TASKS.md):

  ```text
  [C6] step 2: evaluate hard filters + tests
  ```

- Open a PR to `main` using the template; a teammate reviews the diff and the step report.

## Reporting bugs

Use the bug report template in GitHub Issues. Security issues go through
[`SECURITY.md`](SECURITY.md), not public issues.
