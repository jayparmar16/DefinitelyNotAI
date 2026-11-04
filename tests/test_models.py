"""The Claude call path: request shape, structured output, and stop-reason checks."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from askwri.models import MODELS, Image, ModelError, call_claude, call_claude_json
from tests.fake_claude import FakeClaude

SCHEMA = {
    "type": "object",
    "properties": {"topic": {"type": "string"}},
    "required": ["topic"],
    "additionalProperties": False,
}


def test_sends_the_role_model_and_returns_the_reply_text():
    client = FakeClaude("Forests store carbon.")

    reply = call_claude(client, "answerer", document="report.pdf", prompt="Summarise.")

    assert reply == "Forests store carbon."
    request = client.requests[0]
    assert request["model"] == MODELS["answerer"]
    assert request["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "Summarise."}]}
    ]
    assert "output_config" not in request


def test_images_come_before_the_prompt_as_base64_blocks():
    client = FakeClaude("A bar chart.")

    call_claude(
        client,
        "vision",
        document="report.pdf",
        prompt="Describe the figure.",
        images=(Image(b"\x89PNG", "image/png"),),
    )

    first, second = client.requests[0]["messages"][0]["content"]
    assert first == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw=="},
    }
    assert second["type"] == "text"


def test_schema_constrains_the_reply_and_json_is_parsed():
    client = FakeClaude('{"topic": "forests"}')

    label = call_claude_json(
        client, "labeler", document="report.pdf", prompt="Label it.", schema=SCHEMA
    )

    assert label == {"topic": "forests"}
    assert client.requests[0]["output_config"] == {
        "effort": "low",
        "format": {"type": "json_schema", "schema": SCHEMA},
    }


def test_refusal_raises_an_error_naming_the_document():
    refusal = {
        "stop_reason": "refusal",
        "stop_details": SimpleNamespace(category="bio", explanation="declined"),
    }

    with pytest.raises(ModelError, match=r"report\.pdf.*refusal.*bio"):
        call_claude(FakeClaude(refusal), "answerer", document="report.pdf", prompt="Hi")


def test_truncated_reply_raises_instead_of_returning_partial_text():
    truncated = {
        "stop_reason": "max_tokens",
        "content": [SimpleNamespace(type="text", text='{"topic": "fo')],
    }

    with pytest.raises(ModelError, match=r"report\.pdf.*max_tokens"):
        call_claude(FakeClaude(truncated), "labeler", document="report.pdf", prompt="Hi")


def test_api_error_raises_an_error_naming_the_document():
    request = httpx2.Request("POST", "https://bedrock-runtime.invalid")
    client = FakeClaude(anthropic.APIConnectionError(request=request))

    with pytest.raises(ModelError, match=r"report\.pdf.*vision call failed"):
        call_claude(client, "vision", document="report.pdf", prompt="Hi")


def test_a_reply_with_no_text_raises():
    with pytest.raises(ModelError, match=r"report\.pdf.*no text"):
        call_claude(FakeClaude({"content": []}), "answerer", document="report.pdf", prompt="Hi")


def test_embedding_and_rerank_roles_are_not_claude_roles():
    with pytest.raises(ValueError, match="embedder"):
        call_claude(FakeClaude("x"), "embedder", document="report.pdf", prompt="Hi")
