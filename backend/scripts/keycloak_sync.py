"""Bring an existing Keycloak realm up to `keycloak/realm-cashguard.json`.

`--import-realm` seeds the realm on Keycloak's first start only, so a running (or hosted)
Keycloak never gets later additions: a new persona (elena), the `sim` realm role, the
brute-force and password-policy settings. This script adds them over the admin REST API, and is
idempotent (run it as often as you like):

- realm roles and users through `partialImport` with `ifResourceExists: SKIP` (existing ones are
  left alone; new users keep the fixed ids from the file);
- each file user that already existed gets the file's realm roles it is missing (e.g. `sim`);
- the realm's brute-force and password-policy attributes are set to the file's values.

`${VAR:default}` placeholders are filled from the environment like Keycloak's import does
(KC_DEMO_PASSWORD, ...). Clients and the cron service account are not touched. Prints counts,
never a secret.

    uv run python scripts/keycloak_sync.py

Environment: KC_URL (default http://localhost:8081), KC_ADMIN_USER / KC_ADMIN_PASSWORD (dev
defaults admin/admin), KC_DEMO_PASSWORD (default cashguard-dev, as in the realm file).
"""

import json
import os
import re
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

BACKEND = Path(__file__).resolve().parents[1]
REALM_FILE = BACKEND / "keycloak" / "realm-cashguard.json"

# Realm attributes synced from the file (brute-force detection and the password policy).
REALM_SETTINGS = (
    "bruteForceProtected",
    "permanentLockout",
    "maxTemporaryLockouts",
    "bruteForceStrategy",
    "failureFactor",
    "waitIncrementSeconds",
    "maxFailureWaitSeconds",
    "minimumQuickLoginWaitSeconds",
    "quickLoginCheckMilliSeconds",
    "maxDeltaTimeSeconds",
    "passwordPolicy",
)

_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}")


class MissingVariableError(KeyError):
    """A `${VAR}` placeholder without a default, and VAR is not set."""


def substitute(text: str, env: Mapping[str, str]) -> str:
    """Replace every `${VAR:default}` / `${VAR}` with env[VAR], else the default."""

    def repl(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        if name in env:
            return env[name]
        if default is None:
            raise MissingVariableError(name)
        return default

    return _PLACEHOLDER.sub(repl, text)


def load_realm(env: Mapping[str, str], path: Path = REALM_FILE) -> dict[str, Any]:
    """The realm file with its placeholders filled in (substituted inside JSON strings)."""

    def fill(value: Any) -> Any:
        if isinstance(value, str):
            return substitute(value, env)
        if isinstance(value, list):
            return [fill(v) for v in value]
        if isinstance(value, dict):
            return {k: fill(v) for k, v in value.items()}
        return value

    realm: dict[str, Any] = fill(json.loads(path.read_text()))
    return realm


def file_users(realm: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The realm file's people (service accounts belong to clients, which are not synced)."""
    return [u for u in realm.get("users", []) if "serviceAccountClientId" not in u]


def partial_import_payload(realm: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ifResourceExists": "SKIP",
        "roles": {"realm": list(realm.get("roles", {}).get("realm", []))},
        "users": file_users(realm),
    }


def realm_settings(realm: Mapping[str, Any]) -> dict[str, Any]:
    return {k: realm[k] for k in REALM_SETTINGS if k in realm}


def summarize(result: Mapping[str, Any]) -> dict[str, Counter[str]]:
    """partialImport's `results` as {resourceType: Counter(action)}."""
    out: dict[str, Counter[str]] = {}
    for r in result.get("results", []):
        out.setdefault(r["resourceType"], Counter())[r["action"]] += 1
    return out


def admin_token(client: httpx.Client, user: str, password: str) -> str:
    r = client.post(
        "/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": user,
            "password": password,
        },
    )
    r.raise_for_status()
    token: str = r.json()["access_token"]
    return token


def add_missing_realm_roles(client: httpx.Client, realm: Mapping[str, Any]) -> int:
    """Give each existing file user the file's realm roles it lacks; returns how many were added."""
    name = realm["realm"]
    added = 0
    for user in file_users(realm):
        wanted = set(user.get("realmRoles", []))
        found = client.get(
            f"/admin/realms/{name}/users", params={"username": user["username"], "exact": "true"}
        )
        found.raise_for_status()
        if not found.json() or not wanted:
            continue
        uid = found.json()[0]["id"]
        mapped = client.get(f"/admin/realms/{name}/users/{uid}/role-mappings/realm")
        mapped.raise_for_status()
        missing = wanted - {r["name"] for r in mapped.json()}
        if not missing:
            continue
        reps = []
        for role in sorted(missing):
            rr = client.get(f"/admin/realms/{name}/roles/{role}")
            rr.raise_for_status()
            reps.append(rr.json())
        client.post(
            f"/admin/realms/{name}/users/{uid}/role-mappings/realm", json=reps
        ).raise_for_status()
        added += len(reps)
        print(f"  {user['username']}: + {', '.join(sorted(missing))}")
    return added


def main() -> int:
    env = dict(os.environ)
    realm = load_realm(env)
    name = realm["realm"]
    base = env.get("KC_URL", "http://localhost:8081").rstrip("/")
    with httpx.Client(base_url=base, timeout=30) as client:
        token = admin_token(
            client, env.get("KC_ADMIN_USER", "admin"), env.get("KC_ADMIN_PASSWORD", "admin")
        )
        client.headers["Authorization"] = f"Bearer {token}"

        r = client.post(f"/admin/realms/{name}/partialImport", json=partial_import_payload(realm))
        r.raise_for_status()
        result = r.json()
        print(
            f"realm {name} @ {base}: partialImport added {result.get('added', 0)}, "
            f"skipped {result.get('skipped', 0)}"
        )
        for kind, actions in sorted(summarize(result).items()):
            print(f"  {kind}: " + ", ".join(f"{a.lower()} {n}" for a, n in sorted(actions.items())))

        roles_added = add_missing_realm_roles(client, realm)
        print(f"realm roles added to existing users: {roles_added}")

        settings = realm_settings(realm)
        client.put(f"/admin/realms/{name}", json=settings).raise_for_status()
        print(f"realm settings updated: {', '.join(sorted(settings))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
