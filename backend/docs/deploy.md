# Deploying the backend (B14)

> Written by bomboe's session. **Not deployed yet:** the hosting provider is still open (Q22). Everything below works on any Linux VM with Docker ≥ 24 and Compose ≥ 2.24.

## 1. Server
1. A VM (2 vCPU, 4 GB RAM is plenty) with ports 80 and 443 open; Docker + Compose installed.
2. DNS: two A records to the VM: `api.<domain>` and `auth.<domain>`.
3. `git clone` the repo, `cd backend`, `cp .env.example .env` and set **real** values:
   `DOMAIN`, `ANTHROPIC_API_KEY`, `KC_ADMIN_PASSWORD`, `KC_DB_PASSWORD`, `KC_CRON_CLIENT_SECRET`, `KC_DEMO_PASSWORD`. `.env` never leaves the server.

## 2. Start
```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
docker compose exec api python -m app.db.seed --reset      # the demo personas
scripts/smoke_remote.sh https://api.<domain> https://auth.<domain>
```
- Caddy gets TLS certificates automatically and proxies `api.<domain>` → api:8000 (incl. `/ws`) and `auth.<domain>` → keycloak:8080.
- Keycloak runs `start` (production mode) with `KC_HOSTNAME=https://auth.<domain>` and proxy headers, and the API checks `KEYCLOAK_ISSUER=https://auth.<domain>/realms/cashguard`: every token's `iss` matches, whoever asked for it (phone, emulator, scripts) (D36).
- Only 80/443 are public: Postgres, Keycloak and the API have no host ports.
- Cron runs only `process recover` (`CRON_ENABLED_JOBS`); the day jobs are driven by `/sim/next-day` during the demo (Q21).

## 3. After each deploy
Run `scripts/smoke_remote.sh` and paste its output in the step report. Then write the public URLs into `DGAREADME1.md` (closes Q22).

## 4. Rollback / reset
- `POST /api/sim/reset` (any persona token) puts every persona back to its seed state.
- `docker compose ... down` keeps the volumes (`db-data`, `caddy-data`); `down -v` deletes them.
