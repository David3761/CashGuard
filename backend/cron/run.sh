#!/bin/sh
# Usage: run.sh [--dry-run] <endpoint>
# Gets a client-credentials token for `savings-cron` from Keycloak, then POSTs to
# $API_URL/internal/<endpoint> (arch §10). Jobs not in CRON_ENABLED_JOBS are skipped.
set -eu

dry_run=0
if [ "${1:-}" = "--dry-run" ]; then
    dry_run=1
    shift
fi

if [ "$#" -lt 1 ]; then
    echo "usage: run.sh [--dry-run] <endpoint>" >&2
    exit 2
fi
endpoint="$1"

case "$endpoint" in
    "" | *[!a-z-]*)
        echo "run.sh: invalid endpoint '$endpoint' (lowercase letters and dashes only)" >&2
        exit 2
        ;;
esac

: "${API_URL:?API_URL is not set}"
: "${KEYCLOAK_TOKEN_URL:?KEYCLOAK_TOKEN_URL is not set}"
CRON_CLIENT_ID="${CRON_CLIENT_ID:-savings-cron}"
CRON_ENABLED_JOBS="${CRON_ENABLED_JOBS:-all}"

case " $CRON_ENABLED_JOBS " in
    " all " | *" $endpoint "*) ;;
    *)
        echo "$(date -Iseconds) skip $endpoint (not in CRON_ENABLED_JOBS)"
        exit 0
        ;;
esac

url="$API_URL/internal/$endpoint"
if [ "$dry_run" -eq 1 ]; then
    echo "POST $url"
    exit 0
fi

if [ -z "${CRON_CLIENT_SECRET:-}" ]; then
    echo "run.sh: CRON_CLIENT_SECRET is not set" >&2
    exit 2
fi

response=$(curl -fsS -d grant_type=client_credentials -d "client_id=$CRON_CLIENT_ID" \
    --data-urlencode "client_secret=$CRON_CLIENT_SECRET" "$KEYCLOAK_TOKEN_URL")
token=$(printf '%s' "$response" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
if [ -z "$token" ]; then
    echo "run.sh: no access_token from Keycloak" >&2
    exit 1
fi

echo "$(date -Iseconds) POST $url"
curl -fsS -X POST -H "Authorization: Bearer $token" "$url"
echo
