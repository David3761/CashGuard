# Security policy

CashGuard is a hackathon project (VibeHack 2026). It runs on synthetic data only: no real bank
accounts, cards or customers. We still take security reports seriously.

## Reporting a vulnerability

**Please don't open a public issue for a security problem.**

- Use GitHub's private vulnerability reporting: the repository's **Security** tab →
  **Report a vulnerability** (<https://github.com/David3761/CashGuard/security/advisories/new>).
- If that isn't available to you, open an issue that only asks a maintainer to contact you,
  without any details.

Include what you found, where (file, endpoint or commit), how to reproduce it and the impact you
expect. If the report involves a leaked credential, say so in the title: we rotate first and
investigate after.

## Supported versions

| Version | Supported |
|---|---|
| `main` (latest commit) | yes |
| any other branch, tag or fork | no |

## Response timeline

| Step | Target |
|---|---|
| Acknowledge the report | within 3 days |
| First assessment (valid or not, severity) | within 7 days |
| Fix or mitigation for a confirmed high/critical issue | within 14 days |
| Public advisory | after the fix is on `main`, crediting the reporter unless they prefer not |

## Security design (short)

The full design is in
[`backend/docs/savings-coach-backend-architecture.md`](backend/docs/savings-coach-backend-architecture.md)
(§5 auth, §6 the AI agent).

**Authentication and authorisation**

- `/api/*`: every request needs a **Keycloak JWT** (signature checked against the realm's JWKS,
  plus issuer, audience and expiry). The user is always taken from the token's `sub`, never from
  the request body.
- `/api/internal/*` (the scheduled jobs): only tokens with the `internal` realm role, which only
  the confidential `savings-cron` client (client-credentials grant) has. The mobile app never calls
  these endpoints.
- `/api/sim/*` (the demo simulator, which moves the clock and feeds synthetic transactions): mounted
  **only when `SIM_MODE=true`**, and every route also needs the realm role **`sim`** (the demo
  operator; a plain login gets 403).
- Only **access tokens** are accepted (`typ: Bearer`): a Keycloak ID or refresh token is refused.
  RS256 only (`alg: none` and HS256-with-the-public-key are rejected and tested); `iss`,
  `exp`/`nbf` (30 s leeway) and `azp`/`aud` are checked.
- Keycloak: brute-force detection on, password policy `length(12)`, no self-registration; the
  admin console is not reachable on the public site (Caddy answers 404 for `/admin`).

**Abuse limits**

- Rate limits per user (`app/security/ratelimit.py`): `/api/chat` 10/min and 200/day, `/api/sim`
  30/min, WebSocket connects 10/min (`RATE_LIMIT_*`); 429 with `Retry-After`.
- One chat run at a time per user, claimed atomically (409 `agent_busy`).
- Request bodies over 64 KiB → 413 (in the app and at Caddy); soft notes ≤ 2000 characters.
- WebSocket: at most 3 sockets per user, inbound frames ≤ 4 KiB (uvicorn caps frames at 64 KiB),
  and the token's `exp` is re-checked on every message and ping (close 4401).

**HTTP and containers**

- Every response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Content-Security-Policy: default-src 'none'`,
  `Cache-Control: no-store` on `/api/*`, and HSTS (app outside the simulator, and Caddy).
- No CORS: the only client is the mobile app, so no browser origin is allowed.
- `/api/docs` and `/api/openapi.json` only with `API_DOCS_ENABLED=true` (off when hosted).
- The api container runs as an unprivileged user with a HEALTHCHECK; uvicorn trusts
  `X-Forwarded-*` only from the proxy and sends no `server` banner.

**Secrets**

- No secrets are committed. Configuration comes from environment variables or `backend/.env`,
  which is gitignored; `backend/.env.example` lists every variable with empty or dev-only values,
  and a test fails if a key-shaped value appears in it.
- Settings keep API keys and client secrets as `SecretStr` (never printed); logs and stored
  errors go through a redaction filter (Anthropic keys, `Bearer` tokens, JWTs, URL passwords).
- [`.gitleaks.toml`](.gitleaks.toml) configures secret scanning (`gitleaks git`), also run as a
  pre-commit hook. The only allowlisted strings are the obviously fake keys in the tests.

### LLM safeguards

The coach is a Claude agent that can call tools on the user's data. The guard rails are in code,
not only in the prompt:

- **Tool whitelist:** only functions in the tool registry can be called; a tool name is never
  resolved with `getattr`/`eval`. The tool list is rebuilt per run, so the model only sees what is
  allowed in that context.
- **Validated inputs:** every tool input is validated with Pydantic (and the tool schemas are
  `strict`, `additionalProperties: false`). Invalid input goes back to the model as a tool error;
  it never reaches the database.
- **`user_id` is never a tool input:** the backend injects the user from the authenticated
  request, so the model cannot address another user's data.
- **Proactive runs are read-only:** when the agent starts a conversation itself (a new transaction,
  a scheduled job), it only gets read tools and `simulate_plan`; changes happen only after the
  user replies.
- **Banned-phrase filter:** the reply is checked in code for judgemental phrases (RO and EN,
  inflections included); a hit regenerates once, then falls back to a template.
- **Prompt injection:** merchant names, item names and transaction descriptions are treated as
  data; the system prompt tells the model to ignore any instruction inside them, and the context
  snapshot carries no IBANs, card numbers or addresses.
- **Bounded runs:** a maximum number of agent iterations per run (`MAX_AGENT_ITERATIONS`, default
  6), `max_tokens` per call, timeouts on every model call, and a templated fallback reply when a
  limit, an API error, a refusal or a cut-off reply is hit. <!-- PORTS -->Every tool call is logged in the
  `tool_calls` table.<!-- /PORTS -->
- **Rate limits** on the chat, simulator and WebSocket endpoints (see Abuse limits above).

## Development-only defaults

`backend/docker-compose.yml`, the Keycloak realm file and `backend/.env.example` contain
**development defaults that must be changed before any real deployment**:

- Keycloak admin `admin` / `admin` (`KC_ADMIN_USER`, `KC_ADMIN_PASSWORD`).
- Postgres `cashguard` / `cashguard` and the Keycloak database password `keycloak`
  (`KC_DB_PASSWORD`).
- The cron client secret `dev-cron-secret` (`KC_CRON_CLIENT_SECRET`).
- The demo personas' password `cashguard-dev` (`KC_DEMO_PASSWORD`), and the dev/test client that
  allows the password grant (disable it).
- `SIM_MODE=true` (turn it off), Keycloak in `start-dev` mode over plain HTTP, and the database and
  Keycloak ports published on the host.

The hosted overlay (`backend/deploy/docker-compose.prod.yml`) **requires** every one of these
secrets (`${VAR:?}`: compose refuses to start without them), puts everything behind HTTPS and
publishes only the reverse proxy. The cron container still runs as root (busybox crond can't run
jobs unprivileged); it has no port and no data, and runs with `no-new-privileges`.

## Not secrets, by design

- **`mobile/android/app/google-services.json`** is the Firebase client configuration. Firebase
  API keys in client configs only identify the project; they are meant to ship inside the app and
  are not credentials. Access is controlled by Firebase security rules and API restrictions in
  the Google Cloud console.
- **`mobile/android/app/debug.keystore`** is an Android *debug* signing key (well-known password),
  used only for local debug builds; release builds are not signed with it.
- `.gitleaks.toml` allowlists exactly these values plus the fake test credentials, each by file
  **and** value, so a real secret in the same file is still reported. CI runs gitleaks over the
  whole history and `pip-audit` on the locked dependencies.
