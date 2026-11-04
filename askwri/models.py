"""Model registry and Claude call path: every model call picks its model by role.

Run `python -m askwri.models smoke` to make one real call per Claude role.
"""

import argparse
import base64
import json
import sys
from dataclasses import dataclass

import anthropic

# Global inference profiles: the only way to call these Claude models in a US region.
MODELS = {
    "vision": "global.anthropic.claude-sonnet-5-5",
    "labeler": "global.anthropic.claude-haiku-5-5",
    "answerer": "global.anthropic.claude-sonnet-5-5",
    "embedder": "us.cohere.embed-v4:0",  # multilingual, 1,024 dimensions (#33)
    "reranker": "amazon.rerank-v1:0",
}
CLAUDE_ROLES = ("vision", "labeler", "answerer")
# Room for the adaptive thinking these models always do, plus the reply.
MAX_TOKENS = 8192


class ModelError(Exception):
    """A model call failed or was refused; the message names the document it was for."""


@dataclass(frozen=True)
class Image:
    """An image to send to a vision call."""

    data: bytes
    media_type: str  # for example "image/png"


def claude_client() -> anthropic.AnthropicBedrock:
    """Return a client for Claude on Bedrock's bedrock-runtime endpoint.

    Requests are signed (SigV4) with credentials from the standard AWS chain: environment
    variables, the AWS profile, or the task role. The region comes from AWS_REGION or
    AWS_DEFAULT_REGION (us-west-2 for this project); the SDK raises if neither is set.
    """
    return anthropic.AnthropicBedrock()


def call_claude(
    client,
    role: str,
    *,
    document: str,
    prompt: str,
    images: list[Image] = (),
    schema: dict | None = None,
) -> str:
    """Send one prompt (with optional images) to the model for `role` and return its text.

    With `schema` (a JSON Schema), the reply is constrained to match it and is JSON text.
    `document` names what the call is about; it is the first thing in every error.
    Raises ModelError if the API call fails or the model does not finish normally
    (a refusal, or running out of max_tokens).
    """
    if role not in CLAUDE_ROLES:
        raise ValueError(f"{role!r} is not a Claude role; use one of {CLAUDE_ROLES}")
    content = [_image_block(image) for image in images]
    content.append({"type": "text", "text": prompt})
    options = (
        {"output_config": {"format": {"type": "json_schema", "schema": schema}}} if schema else {}
    )
    try:
        response = client.messages.create(
            model=MODELS[role],
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": content}],
            **options,
        )
    except anthropic.APIError as error:
        raise ModelError(f"{document}: {role} call failed: {error}") from error
    return _reply_text(document, role, response)


def call_claude_json(client, role: str, *, schema: dict, **kwargs) -> dict:
    """Like call_claude with a schema, but returns the parsed JSON object."""
    return json.loads(call_claude(client, role, schema=schema, **kwargs))


def _image_block(image: Image) -> dict:
    data = base64.standard_b64encode(image.data).decode("ascii")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": image.media_type, "data": data},
    }


def _reply_text(document: str, role: str, response) -> str:
    """Return the reply text, or raise ModelError unless the model finished normally."""
    if response.stop_reason != "end_turn":
        details = response.stop_details
        reason = (
            f"{response.stop_reason} ({details.category}: {details.explanation})"
            if details
            else response.stop_reason
        )
        raise ModelError(f"{document}: {role} call did not finish: {reason}")
    text = "".join(block.text for block in response.content if block.type == "text")
    if not text:
        raise ModelError(f"{document}: {role} call returned no text")
    return text


def _red_square_png() -> bytes:
    # Imported here so the agent runtime can import the registry without PyMuPDF installed.
    import pymupdf

    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 64, 64), False)
    pixmap.set_rect(pixmap.irect, (255, 0, 0))
    return pixmap.tobytes("png")


def smoke(client) -> bool:
    """Make one tiny call per Claude role, print success or the exact error, return all-ok."""
    colour_schema = {
        "type": "object",
        "properties": {"colour": {"type": "string"}},
        "required": ["colour"],
        "additionalProperties": False,
    }
    calls = {
        "vision": lambda: call_claude(
            client,
            "vision",
            document="smoke",
            prompt="Reply with the one-word colour of this image.",
            images=[Image(_red_square_png(), "image/png")],
        ),
        "labeler": lambda: call_claude_json(
            client,
            "labeler",
            document="smoke",
            prompt="What colour is a ripe banana?",
            schema=colour_schema,
        ),
        "answerer": lambda: call_claude(
            client, "answerer", document="smoke", prompt="Reply with the word: ok"
        ),
    }
    ok = True
    for role, call in calls.items():
        try:
            reply = call()
        except ModelError as error:  # report every role's result, not just the first failure
            ok = False
            print(f"FAIL {role} ({MODELS[role]}): {error}")
        else:
            print(f"PASS {role} ({MODELS[role]}): {reply!r}")
    return ok


def main() -> int:
    """Run the smoke command. Returns the exit code: 1 if any role's call failed, else 0."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["smoke"])
    parser.parse_args()
    return 0 if smoke(claude_client()) else 1


if __name__ == "__main__":
    sys.exit(main())
