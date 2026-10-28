"""The Keycloak realm we import at startup (B1, arch 5.1)."""

import json
from pathlib import Path

import pytest

REALM_FILE = Path(__file__).resolve().parents[2] / "keycloak" / "realm-cashguard.json"

PERSONA_IDS = {
    "matei": "a0000000-0000-4000-8000-000000000001",
    "andrei": "a0000000-0000-4000-8000-000000000002",
    "bianca": "a0000000-0000-4000-8000-000000000003",
    "ioana": "a0000000-0000-4000-8000-000000000004",
    "alex": "a0000000-0000-4000-8000-000000000005",
}


@pytest.fixture(scope="module")
def realm() -> dict:
    return json.loads(REALM_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def clients(realm) -> dict[str, dict]:
    return {c["clientId"]: c for c in realm["clients"]}


def persona_users(realm) -> list[dict]:
    return [u for u in realm["users"] if "serviceAccountClientId" not in u]


def test_realm_is_cashguard_and_enabled(realm):
    assert realm["realm"] == "cashguard"
    assert realm["enabled"] is True


def test_realm_has_exactly_our_three_clients(clients):
    assert set(clients) == {"savings-frontend", "savings-cron", "savings-dev"}


def test_frontend_client_is_public_auth_code_with_pkce_s256(clients):
    c = clients["savings-frontend"]
    assert c["publicClient"] is True
    assert c["standardFlowEnabled"] is True
    assert c["directAccessGrantsEnabled"] is False
    assert c["implicitFlowEnabled"] is False
    assert c["serviceAccountsEnabled"] is False
    assert c["attributes"]["pkce.code.challenge.method"] == "S256"


def test_frontend_client_has_app_and_localhost_redirects(clients):
    uris = clients["savings-frontend"]["redirectUris"]
    assert "ro.cashguard.app:/oauthredirect" in uris
    assert "http://localhost:*" in uris


def test_cron_client_is_confidential_service_account_only(clients):
    c = clients["savings-cron"]
    assert c["publicClient"] is False
    assert c["serviceAccountsEnabled"] is True
    assert c["standardFlowEnabled"] is False
    assert c["directAccessGrantsEnabled"] is False


def test_dev_client_allows_password_grant_only_and_says_dev_only(clients):
    c = clients["savings-dev"]
    assert c["directAccessGrantsEnabled"] is True
    assert c["standardFlowEnabled"] is False
    assert c["serviceAccountsEnabled"] is False
    assert "dev" in c["description"].lower() and "only" in c["description"].lower()


def test_realm_defines_internal_role(realm):
    assert "internal" in {r["name"] for r in realm["roles"]["realm"]}


def test_cron_service_account_has_internal_role(realm):
    sa = next(u for u in realm["users"] if u.get("serviceAccountClientId") == "savings-cron")
    assert "internal" in sa["realmRoles"]


def test_five_persona_users_with_fixed_ids(realm):
    users = {u["username"]: u for u in persona_users(realm)}
    assert {name: u["id"] for name, u in users.items()} == PERSONA_IDS


@pytest.mark.parametrize("username", list(PERSONA_IDS))
def test_persona_user_can_log_in_without_setup(realm, username):
    # Keycloak refuses a password grant ("account not fully set up") for incomplete profiles.
    u = next(u for u in persona_users(realm) if u["username"] == username)
    assert u["enabled"] is True
    assert u["emailVerified"] is True
    assert u["email"] and u["firstName"] and u["lastName"]
    assert u.get("requiredActions", []) == []
    creds = [c for c in u["credentials"] if c["type"] == "password"]
    assert len(creds) == 1 and creds[0]["temporary"] is False


def test_secrets_come_from_env_placeholders_not_literals(realm, clients):
    # Keycloak resolves ${VAR:default} at import: dev gets the default, the server sets real values.
    for u in persona_users(realm):
        assert u["credentials"][0]["value"].startswith("${KC_DEMO_PASSWORD:")
    assert clients["savings-cron"]["secret"].startswith("${KC_CRON_CLIENT_SECRET:")


def test_no_persona_user_has_the_internal_role(realm):
    for u in persona_users(realm):
        assert "internal" not in u.get("realmRoles", [])


def test_access_token_lifespan_is_at_least_30_minutes(realm):
    assert realm["accessTokenLifespan"] >= 1800
