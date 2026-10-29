# Night report: 2026-10-29, 03:30 → 07:30

David G. asked for this before going to bed: "merge absolutely everything into main, a full review, find out what the hackathon's code-evaluation software checks and fix our code for it, check everything on GitHub, the best working app, final, don't ask me anything." This page lists what was done, what was checked and what's still open. The decisions are D54–D56 in [DGAREADME1.md](DGAREADME1.md).

## 1. Result

- **`main` holds everything**, tagged **`v1.0-submission`**, and it's pushed. `api-development` and `dga-final` point to the same commit. Every local and remote branch is merged in: `bomboe`, `engine-dev`, `engine-development`, `api-development`, `main`, `dga-final`, every `dga-task/*`, `int-engine-tests`, and the old local `api-ai` notes, which now live in `docs/team/early-ai-design/`.
- **GitHub CI is green** on `main`: the backend job (ruff, mypy, pytest with Postgres), the mobile job (flutter analyze + test) and gitleaks over the full history.
- **Tests:** 4 167 passed, 6 deselected (the paid `live` ones), **94 % coverage**. That covers unit, db, api, ws and acceptance. ruff, mypy strict, the lock check, bandit (0 issues) and gitleaks over the full history (no leaks) are all clean.
- **Scene A, live on Amazon Bedrock**, through the mobile app's API, on the simulator clock:
  1. `/api/sim/reset`, then `POST /api/sim/transaction {"scenario_id": "matei_mega_500"}`.
  2. The proactive run: Claude writes the question itself, "Am văzut 500 de lei la Mega Image azi, mai mult decât de obicei. Ce a fost?"
  3. `POST /assistant/messages` (SSE) with "Am luat și pentru colegi, suntem cinci. Îmi dau banii înapoi." → `annotate_transaction` writes to Postgres. The effective amount becomes 100 lei, a 400-lei receivable is created for "colegi" (4 × 100), and a new plan version is computed.
  4. Claude's reply (≈11 s): "…partea ta e 100 de lei, și de la colegi ai 400 de lei de recuperat (4 × 100 de lei). Bugetul de azi e 115,86 lei. Șansa pentru obiectiv e 76% (era 79%)…"
- **Docker:** the api image builds and runs as a non-root user (uid 10001). Its HEALTHCHECK reports healthy, the security headers are on every response, and the app API answers on a freshly seeded database.

## 2. What got merged (in order)

| Branch | What it brought |
|---|---|
| `origin/engine-dev` (danutu) | the real engine E1–E13, adapted to our F2 types |
| `origin/bomboe` (bomboe) | the platform B1–B15 + F3, on our F1/F2 with a compatibility layer |
| `origin/main` (David V.) | the mobile MVP |
| `dga-task/p1b-…`, `dga-task/p1a-…` | C10–C13, A8, A10 (P1-B); C8 learning rules, C9 propagation, A11 language (P1-A) |
| `dga-task/async-ports` | every port, handler and context shell is async, so it matches bomboe's services and danutu's engine |
| `dga-task/pg-ports` | **Claude's tools write to Postgres** (`backend/app/agent/pg_ports.py`): 21 ports, one unit of work per tool call, every call logged. bomboe's `_fallbacks.py` stand-ins now use our real `apply_annotation` / C9 / C12 |
| `dga-task/app-api` | the root-level API for David V.'s app per `API_SPEC.md`: `/balance`, `/transactions`, `/devices`, `/assistant/messages` (SSE), FCM pushes, plus the rate limiter |
| `dga-task/ai-safety` | the red-team suite (89 tests), a 16-call tool budget per run, a 60 s chat deadline, a 4 000-character message cap, `LLM_MAX_CONCURRENCY`, transfers capped at 100 000 lei with one per run, prompt rules and log redaction; [`backend/docs/ai-safety.md`](../../backend/docs/ai-safety.md) |
| `dga-task/platform-sec` | the `sim` role on `/api/sim/*`, prod secrets made mandatory, the non-root Dockerfile with a HEALTHCHECK, security headers, a 64 KiB body limit, WebSocket caps, the chat race fix, gitleaks allowlists, pip-audit + gitleaks in CI, and bandit cleaned |
| `dga-task/mobile-hardening` | AES-GCM with a random keystore key (was a hard-coded key with a reused IV), `--dart-define` config, widget tests (8/8), iOS ATS limited to localhost, a11y labels, and the unused storage permission removed |
| `dga-task/repo-hygiene` | LICENSE (MIT), CI, SECURITY.md, CONTRIBUTING.md, dependabot, pre-commit, .gitleaks.toml |
| `dga-task/docs-final` | the new README (checked against the code), stale claims fixed, process docs moved to `docs/team/` |

## 3. What the evaluation software checks, and where we stand

The research agent's checklist, built from how hackathon code graders (AI repo graders, Semgrep, Bandit, gitleaks, dependency audits) score a repo:

| Check | Status |
|---|---|
| `main` contains the real code; one-command setup; accurate README | ✅ README rewritten and checked against the code; the stale claims in the docs fixed |
| LICENSE, CI, SECURITY.md, CONTRIBUTING, dependabot, pre-commit | ✅ |
| No secrets in the repo or its history | ✅ gitleaks over every commit: no leaks (the Bedrock key is only in the gitignored `backend/.env`) |
| Rate limiting / quotas on the AI endpoints | ✅ chat 10/min + 200/day per user, sim 30/min, WS connects 10/min, one run at a time per user |
| Prompt injection / excessive agency (OWASP LLM Top 10) | ✅ [`backend/docs/ai-safety.md`](../../backend/docs/ai-safety.md): 34 controls, each with its file and test |
| Unbounded consumption | ✅ max_tokens, timeouts, bounded retries, iteration cap, tool budget, chat deadline, concurrency cap, 64 KiB bodies |
| AuthN/AuthZ, IDOR | ✅ every route needs a token (except health and the single-user app API); queries are user-scoped and tested; only access tokens are accepted |
| Static analysis | ✅ bandit 0 issues; semgrep: the f-string SQL fixed, the Dockerfiles clean (cron has a justified `nosemgrep`) |
| Dependency audit | ✅ pip-audit: no known vulnerabilities (Python 3.12) |
| Container hardening | ✅ api and cron non-root (cron moved to supercronic on 2026-10-29 morning, branch `dga-task/final-hardening`) + HEALTHCHECK |
| Mobile: no hard-coded crypto keys, ATS/cleartext limited | ✅ |

## 4. Bugs found and fixed tonight (beyond the merges)

- **Bedrock streams an empty tool input for tools without arguments.** Our strict check rejected it, so every such chat fell back to "technical problem" (`389da2c`).
- **The proactive timeout of 5 s was always hit on Bedrock**, which always gave the template question. It's 15 s now (D54).
- **The sim rate limit of 5/min would 429 during a quick demo.** It's 30/min now.
- **After `/sim/reset`, `/api/forecast` showed the seeded 79 % instead of the new value**, because it sorted by the sim-clock timestamp. It now sorts by insertion (`77611ea`).
- **After `/sim/reset`, a newly registered phone token could be pruned at once**, giving a 500. Fixed.
- **The chat race:** two parallel posts could both start a run. The claim is atomic now.

## 5. Before the demo (11:00)

1. `backend/.env`: keep `LLM_PROVIDER=bedrock` and the Bedrock API key, and set `APP_API_ENABLED=true` (already set in your local `.env`). Send one test chat right before presenting.
2. **Demo order:** `/api/sim/reset` → `POST /api/sim/transaction {"scenario_id": "matei_mega_500"}` → wait for the question (≤ 15 s) → answer "Am luat și pentru colegi, suntem cinci." The tokens need the realm role `sim`, which the personas get from a fresh realm import.
3. **The app against the backend:** `flutter run --dart-define=USE_MOCK_API=false --dart-define=API_BASE_URL=http://10.0.2.2:8000` (emulator).
4. The first Claude call after a cold start takes ~13 s while the prompt cache is written. Warm it up with one message first.

## 6. Still open (honest list)

- **For David V.:**
  - The app has no UI for quick replies or action cards, so Scene A's answer is typed.
  - There's no iOS Firebase config, so iOS pushes won't arrive.
  - Release builds are signed with the debug keystore.
  - Run one native build per platform; neither was run tonight (no SDK here).
- **For bomboe:**
  - The transfers service should refuse amounts above the balance (`insufficient_funds`, HANDOFFS H-15).
  - `run_proactive` creates no `agent_runs` row, so proactive tool calls aren't audited.
  - A hosted Keycloak that was already seeded needs the `sim` role, brute-force protection and the password policy set by hand (H-16).
  - The `savings-dev` password-grant client is dev-only but still exists in the realm.
- **For danutu:** who lowers a pot when spending is pot-funded (`apply_transaction` vs `save_evaluation`) is still undecided; today only `apply_transaction` does it.
- **Context loader:** it doesn't fill some optional snapshot fields yet (recent days, slips, reflections, life notes), so Claude works with less history than the spec allows.
- **Voice:** the backend produces `speak_text`; the app has no mic or TTS.
- **GitHub settings:** DGAdavid1 has only write access, so the repo description and topics couldn't be set. David V. (the owner) can set them with:
  `gh repo edit David3761/CashGuard --description "CashGuard: a voice-first AI money coach that judges every purchase against your life" --add-topic fintech,ai-agent,claude,amazon-bedrock,fastapi,flutter`
- **Dependabot opened 4 PRs right after the push** (#1–#4; python-dateutil 3.0.0 is a major bump). Don't merge them before the submission.
