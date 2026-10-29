"""app.push.fcm: OAuth with the service-account key, the HTTP v1 body, error handling (respx)."""

import json
import logging
from pathlib import Path

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import Settings
from app.push import bridge
from app.push.fcm import (
    SCOPE,
    FcmSender,
    NullSender,
    ServiceAccount,
    load_service_account,
    message_body,
    sender_from_settings,
)

TOKEN_URI = "https://oauth2.example.test/token"
SEND = "https://fcm.googleapis.com/v1/projects/cashctrl-6b66a/messages:send"
DEVICE = "c0nKB-device-token-0123456789"


@pytest.fixture(scope="module")
def key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def account(key: rsa.RSAPrivateKey) -> ServiceAccount:
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return ServiceAccount("push@cashctrl-6b66a.iam.example", pem, TOKEN_URI, "cashctrl-6b66a")


class Clock:
    def __init__(self) -> None:
        self.t = 1_800_000_000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def sender(account: ServiceAccount, clock: Clock) -> FcmSender:
    return FcmSender(account, client=httpx.AsyncClient(), now=clock)


def token_ok(value: str = "ya29.access", expires_in: int = 3600) -> httpx.Response:
    return httpx.Response(200, json={"access_token": value, "expires_in": expires_in})


def test_the_body_is_data_only_with_string_values():
    body = message_body(DEVICE, {"message": "You received 150 lei from Ioana Stan."})
    assert body == {
        "message": {
            "token": DEVICE,
            "data": {"message": "You received 150 lei from Ioana Stan."},
            "android": {"priority": "high"},
        }
    }
    assert "notification" not in body["message"]


def test_the_jwt_assertion_is_signed_and_scoped(sender, key, clock):
    claims = jwt.decode(
        sender.assertion(),
        key.public_key(),
        algorithms=["RS256"],
        audience=TOKEN_URI,
        options={"verify_exp": False, "verify_iat": False},
    )
    assert claims["iss"] == "push@cashctrl-6b66a.iam.example"
    assert claims["scope"] == SCOPE
    assert claims["exp"] - claims["iat"] == 3600
    assert claims["iat"] == int(clock.t)


@respx.mock
async def test_send_uses_a_cached_access_token(sender, clock):
    oauth = respx.post(TOKEN_URI).mock(return_value=token_ok())
    fcm = respx.post(SEND).mock(return_value=httpx.Response(200, json={"name": "m/1"}))
    assert await sender.send(DEVICE, {"message": "hi"}) == "sent"
    assert await sender.send(DEVICE, {"message": "again"}) == "sent"
    assert oauth.call_count == 1
    assert fcm.call_count == 2
    sent = json.loads(fcm.calls[0].request.content)
    assert sent["message"]["data"] == {"message": "hi"}
    assert fcm.calls[0].request.headers["authorization"] == "Bearer ya29.access"
    clock.t += 3600 - 59  # within the refresh margin → a new token
    await sender.send(DEVICE, {"message": "later"})
    assert oauth.call_count == 2


@respx.mock
@pytest.mark.parametrize(("status", "code"), [(404, "UNREGISTERED"), (403, "SENDER_ID_MISMATCH")])
async def test_gone_tokens_are_reported_dead(sender, status, code):
    respx.post(TOKEN_URI).mock(return_value=token_ok())
    error = {"error": {"status": "NOT_FOUND", "details": [{"errorCode": code}]}}
    respx.post(SEND).mock(return_value=httpx.Response(status, json=error))
    assert await sender.send(DEVICE, {"message": "x"}) == "dead"


@respx.mock
async def test_401_refreshes_the_token_once(sender):
    oauth = respx.post(TOKEN_URI).mock(side_effect=[token_ok("old"), token_ok("new")])
    respx.post(SEND).mock(
        side_effect=[httpx.Response(401, json={}), httpx.Response(200, json={"name": "m/2"})]
    )
    assert await sender.send(DEVICE, {"message": "x"}) == "sent"
    assert oauth.call_count == 2


@respx.mock
async def test_other_failures_are_logged_without_the_token(sender, caplog):
    respx.post(TOKEN_URI).mock(return_value=token_ok())
    respx.post(SEND).mock(
        side_effect=[httpx.Response(500, text="boom"), httpx.ConnectTimeout("slow")]
    )
    with caplog.at_level(logging.WARNING):
        assert await sender.send(DEVICE, {"message": "x"}) == "failed"
        assert await sender.send(DEVICE, {"message": "x"}) == "failed"
    assert DEVICE not in caplog.text
    assert "c0nKB-de" in caplog.text


@respx.mock
async def test_a_failing_oauth_exchange_is_a_failed_push(sender):
    respx.post(TOKEN_URI).mock(return_value=httpx.Response(400, json={"error": "invalid_grant"}))
    assert await sender.send(DEVICE, {"message": "x"}) == "failed"


async def test_null_sender_skips(caplog):
    with caplog.at_level(logging.INFO):
        assert await NullSender().send(DEVICE, {"message": "x"}) == "skipped"
    assert DEVICE not in caplog.text


def test_load_service_account(tmp_path: Path, account):
    path = tmp_path / "key.json"
    path.write_text(
        json.dumps(
            {
                "client_email": account.client_email,
                "private_key": account.private_key,
                "token_uri": account.token_uri,
                "project_id": account.project_id,
                "type": "service_account",
            }
        )
    )
    loaded = load_service_account(path)
    assert loaded == account
    assert account.private_key not in repr(loaded)


@pytest.mark.parametrize(
    ("content", "error"),
    [
        ("{}", "missing client_email, private_key, token_uri, project_id"),
        ("[]", "not a service-account"),
        ("nope", "can't read"),
    ],
)
def test_bad_key_files_name_the_problem_not_the_key(tmp_path: Path, content, error):
    path = tmp_path / "key.json"
    path.write_text(content)
    with pytest.raises(ValueError, match=error):
        load_service_account(path)


def test_sender_from_settings(tmp_path: Path, account):
    assert sender_from_settings(Settings(_env_file=None)) is None
    path = tmp_path / "key.json"
    path.write_text(
        json.dumps(
            {
                "client_email": account.client_email,
                "private_key": account.private_key,
                "token_uri": account.token_uri,
                "project_id": account.project_id,
            }
        )
    )
    made = sender_from_settings(Settings(_env_file=None, FCM_SERVICE_ACCOUNT_FILE=path))
    assert isinstance(made, FcmSender)


def test_push_data_is_all_strings():
    data = bridge.push_data(
        {"id": 7, "type": "overspend", "title": "Buget", "body": "Ai depășit.", "opens_chat": True}
    )
    assert data == {
        "message": "Ai depășit.",
        "title": "Buget",
        "type": "overspend",
        "notification_id": "7",
        "opens_chat": "true",
    }
    assert bridge.push_data({"title": "Only a title"})["message"] == "Only a title"
