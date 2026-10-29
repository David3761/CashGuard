#!/bin/sh
# B1 step 4: bring the local stack up and check the whole chain (compose → Keycloak → API → cron).
#   scripts/smoke_local.sh            (from backend/; reseeds the dev DB)
set -eu
cd "$(dirname "$0")/.."

API="${API:-http://localhost:8000/api}"
KC="${KC:-http://localhost:8081/realms/cashguard}"
PASSWORD="${KC_DEMO_PASSWORD:-cashguard-dev}"
CRON_SECRET="${KC_CRON_CLIENT_SECRET:-dev-cron-secret}"

step() { printf '\n== %s\n' "$*"; }
token() { sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p'; }

step "compose up (db, keycloak, api, cron)"
docker compose up -d --build --wait db keycloak api
docker compose up -d cron

step "health"
curl -fsS "$API/health"; echo

step "seed the personas"
docker compose exec -T api python -m app.db.seed --reset

step "token for matei (savings-dev, password grant)"
USER_TOKEN=$(curl -fsS -d grant_type=password -d client_id=savings-dev -d username=matei \
  --data-urlencode "password=$PASSWORD" "$KC/protocol/openid-connect/token" | token)
[ -n "$USER_TOKEN" ] || { echo "no user token" >&2; exit 1; }

step "GET /me"
curl -fsS -H "Authorization: Bearer $USER_TOKEN" "$API/me"; echo

step "GET /state"
curl -fsS -H "Authorization: Bearer $USER_TOKEN" "$API/state" | head -c 300; echo

step "cron token (savings-cron, client credentials) → POST /internal/process"
CRON_TOKEN=$(curl -fsS -d grant_type=client_credentials -d client_id=savings-cron \
  --data-urlencode "client_secret=$CRON_SECRET" "$KC/protocol/openid-connect/token" | token)
curl -fsS -X POST -H "Authorization: Bearer $CRON_TOKEN" "$API/internal/process"; echo

step "a user token on /internal is refused"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Authorization: Bearer $USER_TOKEN" \
  "$API/internal/process")
[ "$code" = "403" ] || { echo "expected 403, got $code" >&2; exit 1; }
echo "403 ok"

step "Scene A: matei_mega_500 through the simulator"
curl -fsS -X POST -H "Authorization: Bearer $USER_TOKEN" -H "Content-Type: application/json" \
  -d '{"scenario_id":"matei_mega_500"}' "$API/sim/transaction"; echo

printf '\nSMOKE OK\n'
