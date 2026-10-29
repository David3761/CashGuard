#!/bin/sh
# B14 step 2: check a hosted deployment end to end.
#   scripts/smoke_remote.sh https://api.example.ro https://auth.example.ro
set -eu
cd "$(dirname "$0")/.."

BASE="${1:?usage: smoke_remote.sh <api base URL> <auth base URL>}"
AUTH="${2:?usage: smoke_remote.sh <api base URL> <auth base URL>}"
API="$BASE/api"
KC="$AUTH/realms/cashguard"
PASSWORD="${KC_DEMO_PASSWORD:?set KC_DEMO_PASSWORD (the persona password on the server)}"

step() { printf '\n== %s\n' "$*"; }

step "health"
curl -fsS "$API/health"; echo

step "token for matei via savings-dev"
TOKEN=$(curl -fsS -d grant_type=password -d client_id=savings-dev -d username=matei \
  --data-urlencode "password=$PASSWORD" "$KC/protocol/openid-connect/token" \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
[ -n "$TOKEN" ] || { echo "no token" >&2; exit 1; }

step "GET /me (the token's iss must equal the API's KEYCLOAK_ISSUER)"
curl -fsS -H "Authorization: Bearer $TOKEN" "$API/me"; echo

step "WebSocket through the proxy (Upgrade headers)"
WS="$(printf '%s' "$BASE" | sed 's#^http#ws#')/ws?token=$TOKEN"
WS_URL="$WS" uv run python -c '
import asyncio, os, websockets
async def main():
    async with websockets.connect(os.environ["WS_URL"], open_timeout=10):
        print("ws connected")
asyncio.run(main())'

step "POST /sim/reset"
curl -fsS -o /dev/null -w '%{http_code}\n' -X POST -H "Authorization: Bearer $TOKEN" \
  "$API/sim/reset"

if [ -f scripts/demo_client.py ]; then
  step "Scene A (demo client, D4)"
  uv run python scripts/demo_client.py --base "$BASE" --scene A
else
  step "Scene A skipped: scripts/demo_client.py (David G., D4) not merged yet"
fi
printf '\nREMOTE SMOKE OK\n'
