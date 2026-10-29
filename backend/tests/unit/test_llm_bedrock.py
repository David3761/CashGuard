"""LLM_PROVIDER=bedrock: the hackathon's Amazon Bedrock path (bedrock-runtime, SigV4)."""

import httpx2
import pytest
from anthropic import AsyncAnthropicBedrock

from app.agent.llm import LLM, BedrockAuth, LLMError, LLMUnavailable, bedrock_model_id
from app.config import Settings

AWS = {
    "LLM_PROVIDER": "bedrock",
    "AWS_DEFAULT_REGION": "us-west-2",
    "AWS_ACCESS_KEY_ID": "AKIDEXAMPLE",
    "AWS_SECRET_ACCESS_KEY": "secret-example",
    "AWS_SESSION_TOKEN": "token-example",
}


def _bedrock_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **{**AWS, **overrides})  # type: ignore[arg-type]


def test_bedrock_settings_build_the_bedrock_client_with_the_inference_profile() -> None:
    llm = LLM.from_settings(_bedrock_settings())

    assert isinstance(llm._client, AsyncAnthropicBedrock)
    assert str(llm._client.base_url).startswith("https://bedrock-runtime.us-west-2.amazonaws.com")
    assert llm._model == "us.anthropic.claude-sonnet-5-5"


def test_refusal_fallback_is_always_off_on_bedrock() -> None:
    llm = LLM.from_settings(_bedrock_settings(ANTHROPIC_REFUSAL_FALLBACK=True))

    assert llm._refusal_fallback is False


@pytest.mark.parametrize(
    ("model", "region", "expected"),
    [
        ("claude-sonnet-5-5", "us-west-2", "us.anthropic.claude-sonnet-5-5"),
        ("claude-sonnet-5-5", "eu-central-1", "eu.anthropic.claude-sonnet-5-5"),
        ("claude-haiku-5-5", "ap-southeast-2", "apac.anthropic.claude-haiku-5-5"),
        ("us.anthropic.claude-opus-5-5", "us-west-2", "us.anthropic.claude-opus-5-5"),
    ],
)
def test_bedrock_model_ids(model: str, region: str, expected: str) -> None:
    assert bedrock_model_id(model, region) == expected


@pytest.mark.parametrize(
    "missing", ["AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
)
async def test_missing_aws_settings_disable_the_client(missing: str) -> None:
    llm = LLM.from_settings(_bedrock_settings(**{missing: None}))

    assert llm._client is None
    with pytest.raises(LLMUnavailable):
        await llm.create(["rules"], [{"role": "user", "content": "salut"}])


async def test_a_bedrock_request_is_signed_and_sent_to_bedrock_runtime() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(
            403, json={"type": "error", "error": {"type": "permission_error", "message": "x"}}
        )

    llm = LLM(
        api_key=None,
        model="claude-sonnet-5-5",
        effort="low",
        refusal_fallback=False,
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        bedrock=BedrockAuth("us-west-2", "AKIDEXAMPLE", "secret-example", "token-example"),
    )
    with pytest.raises(LLMError):  # a 403: only the outgoing request matters here
        await llm.create(["rules"], [{"role": "user", "content": "salut"}])
    await llm.aclose()

    assert seen, "nothing was sent"
    request = seen[0]
    assert request.url.host == "bedrock-runtime.us-west-2.amazonaws.com"
    assert request.headers["authorization"].startswith("AWS4-HMAC-SHA256")
    assert "secret-example" not in str(request.headers)
