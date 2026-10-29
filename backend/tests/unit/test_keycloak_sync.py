"""scripts/keycloak_sync.py: placeholder substitution and the payloads it sends (no network)."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

BACKEND = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "keycloak_sync", BACKEND / "scripts" / "keycloak_sync.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["keycloak_sync"] = module
    spec.loader.exec_module(module)
    return module


ks = _load()


def test_substitute_uses_env_then_default():
    assert ks.substitute("${KC_DEMO_PASSWORD:cashguard-dev}", {}) == "cashguard-dev"
    assert ks.substitute("${KC_DEMO_PASSWORD:cashguard-dev}", {"KC_DEMO_PASSWORD": "p"}) == "p"
    assert ks.substitute("a-${X:1}-${Y:2}", {"Y": "y"}) == "a-1-y"
    assert ks.substitute("${EMPTY:x}", {"EMPTY": ""}) == ""  # set but empty wins, like Keycloak
    assert ks.substitute("no placeholders", {}) == "no placeholders"


def test_substitute_default_may_be_empty_and_missing_without_default_fails():
    assert ks.substitute("${X:}", {}) == ""
    with pytest.raises(ks.MissingVariableError):
        ks.substitute("${NOT_SET_ANYWHERE}", {})


def test_load_realm_fills_every_placeholder():
    realm = ks.load_realm({"KC_DEMO_PASSWORD": "demo-pass-1234", "KC_CRON_CLIENT_SECRET": "s"})
    assert "${" not in json.dumps(realm)
    elena = next(u for u in realm["users"] if u["username"] == "elena")
    assert elena["credentials"][0]["value"] == "demo-pass-1234"
    cron = next(c for c in realm["clients"] if c["clientId"] == "savings-cron")
    assert cron["secret"] == "s"


@pytest.fixture
def realm():
    return ks.load_realm({})


def test_partial_import_payload_skips_existing_and_keeps_ids(realm):
    payload = ks.partial_import_payload(realm)
    assert payload["ifResourceExists"] == "SKIP"
    assert {r["name"] for r in payload["roles"]["realm"]} >= {"internal", "sim"}
    users = {u["username"]: u for u in payload["users"]}
    assert users["elena"]["id"] == "a0000000-0000-4000-8000-000000000006"
    assert "sim" in users["elena"]["realmRoles"]
    assert users["elena"]["credentials"][0]["value"] == "cashguard-dev"
    # clients (and so their service accounts) are not synced
    assert "clients" not in payload
    assert not any("serviceAccountClientId" in u for u in payload["users"])
    assert len(payload["users"]) == len(realm["users"]) - 1


def test_realm_settings_are_brute_force_and_password_policy(realm):
    settings = ks.realm_settings(realm)
    assert settings["bruteForceProtected"] is True
    assert settings["passwordPolicy"].startswith("length(12)")
    assert set(settings) <= set(ks.REALM_SETTINGS)
    assert not {"users", "clients", "roles", "realm"} & set(settings)


def test_summarize_counts_actions_per_resource_type():
    result = {
        "results": [
            {"action": "ADDED", "resourceType": "USER", "resourceName": "elena", "id": "x"},
            {"action": "SKIPPED", "resourceType": "USER", "resourceName": "matei", "id": "y"},
            {"action": "SKIPPED", "resourceType": "REALM_ROLE", "resourceName": "sim", "id": "z"},
        ]
    }
    summary = ks.summarize(result)
    assert summary["USER"] == {"ADDED": 1, "SKIPPED": 1}
    assert summary["REALM_ROLE"] == {"SKIPPED": 1}
