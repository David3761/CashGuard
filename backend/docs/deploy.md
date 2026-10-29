# Deploying the backend (B14)

> Written by bomboe's session. **Not deployed yet:** the hosting provider is still open (Q22). Everything below works on any Linux VM with Docker ≥ 24 and Compose ≥ 2.24.

## 1. Server
1. A VM (2 vCPU, 4 GB RAM is plenty) with ports 80 and 443 open; Docker + Compose installed.
2. DNS: two A records to the VM: `api.<domain>` and `auth.<domain>`.
3. `git clone` the repo, `cd backend`, `cp .env.example .env` and set **real** values:
   `DOMAIN`, the LLM credentials, and the secrets the
   prod overlay **requires**: `POSTGRES_PASSWORD`, `KC_DB_PASSWORD`, `KC_ADMIN_USER`,
   `KC_ADMIN_PASSWORD`, `KC_CRON_CLIENT_SECRET`, `KC_DEMO_PASSWORD` (at least 12 characters: the
   realm's password policy) and `APP_API_KEY` (the Flutter app's shared key, e.g.
   `openssl rand -hex 32`; build the app with `--dart-define=APP_API_KEY=<the same value>`).
   `.env` never leaves the server.
   - A Keycloak whose realm was imported before a realm-file change (new personas, the `sim`
     role, the password policy): run `make keycloak-sync` on the server (`KC_URL` = the Keycloak
     port or an SSH tunnel, since Caddy hides `/admin`; the prod `KC_ADMIN_*`).
   - **LLM credentials**, one provider: Amazon Bedrock with `LLM_PROVIDER=bedrock`,
     `AWS_DEFAULT_REGION=us-west-2` and a Bedrock API key in `AWS_BEARER_TOKEN_BEDROCK` (or the
     temporary `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN`, which expire);
     the model runs as the inference profile `us.anthropic.claude-sonnet-5-5`. Or the Claude API
     with `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`. Without either, the agent answers with
     templates.
   - The values in `docker-compose.yml` and `.env.example` (`admin`/`admin`, `cashguard`,
     `keycloak`, `dev-cron-secret`, `cashguard-dev`) are **DEV-ONLY defaults**. The prod overlay
     uses `${VAR:?}` for each secret, so `docker compose up` stops with "set VAR" instead of
     starting with a dev default.
   - An existing Postgres volume keeps its first password: after changing `POSTGRES_PASSWORD`,
     run `ALTER USER cashguard PASSWORD '…'` once.

## 2. Start
```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
docker compose exec api python -m app.db.seed --reset      # the demo personas
scripts/smoke_remote.sh https://api.<domain> https://auth.<domain>
```
- Caddy gets TLS certificates automatically and proxies `api.<domain>` → api:8000 (incl. `/ws`) and `auth.<domain>` → keycloak:8080.
- Keycloak runs `start` (production mode) with `KC_HOSTNAME=https://auth.<domain>` and proxy headers, and the API checks `KEYCLOAK_ISSUER=https://auth.<domain>/realms/cashguard`: every token's `iss` matches, whoever asked for it (phone, emulator, scripts) (D36).
- Only 80/443 are public: Postgres, Keycloak and the API have no host ports.
- The **Keycloak admin console is not public**: Caddy answers 404 for `/admin` and `/admin/*` on
  `auth.<domain>`. To administer it: `ssh -L 8080:localhost:8080 <vm>` plus a temporary port
  mapping, or `docker compose exec keycloak /opt/keycloak/bin/kcadm.sh …`.
- `SIM_MODE` is on for the hosted demo (`${SIM_MODE:-true}`): `/api/sim/*` needs the realm role
  `sim` (the five demo personas have it) and is rate limited. Set `SIM_MODE=false` for anything
  that isn't the demo; the routes are then not mounted at all.
- `/api/docs` and `/api/openapi.json` are off (`API_DOCS_ENABLED=false`).
- The api runs as an unprivileged user with a HEALTHCHECK, behind Caddy with
  `--proxy-headers --forwarded-allow-ips '*'` (only Caddy can reach it), no `server` banner and
  64 KiB WebSocket frames. Bodies over 64 KiB are refused at Caddy and in the app (413).
- **Realm import runs only on the first start** (`--import-realm` skips an existing realm). On a
  Keycloak seeded before 2026-10-29, add by hand: the realm role `sim` (to the personas), brute
  force detection (Realm settings → Security defenses) and the password policy `length(12)`.
- `savings-dev` (password grant) is a **DEV/TEST client**. The hosted demo keeps it for
  `scripts/smoke_remote.sh`, limited by brute-force protection and the required persona
  password. On any real deployment, disable it (Clients → savings-dev → Enabled off).
- Cron runs only `process recover` (`CRON_ENABLED_JOBS`); the day jobs are driven by `/sim/next-day` during the demo (Q21).

## 3. After each deploy
Run `scripts/smoke_remote.sh` and paste its output in the step report. Then write the public URLs into `docs/team/DGAREADME1.md` (closes Q22).

## 4. Rollback / reset
- `POST /api/sim/reset` (a token with the realm role `sim`, e.g. a demo persona) puts every persona back to its seed state.
- `docker compose ... down` keeps the volumes (`db-data`, `caddy-data`); `down -v` deletes them.
