"""Claude on Bedrock with JSON Schema structured output; every call is traced.

Model IDs come from ASKWRI_SMALL_MODEL (Haiku-class: planning, rewrites, checks) and
ASKWRI_LARGE_MODEL (Sonnet-class: the final answer), set by Terraform.
"""

import json
import os

import anthropic

from askwri.agent import usage
from askwri.agent.tracing import chat_span, finish_chat_span

SMALL = "ASKWRI_SMALL_MODEL"
LARGE = "ASKWRI_LARGE_MODEL"
MAX_TOKENS = 8192  # room for the adaptive thinking these models do, plus the reply


class ModelError(Exception):
    """A model call did not finish normally (refusal, truncation) or returned no text."""


def client() -> anthropic.AnthropicBedrock:
    """Claude client signed (SigV4) with the runtime role or local AWS profile."""
    return anthropic.AnthropicBedrock()


def ask_json(
    client,
    size: str,
    *,
    step: str,
    system: str,
    prompt: str,
    schema: dict,
    effort: str | None = None,
) -> dict:
    """One model call whose reply must match `schema`; returns the parsed object.

    `size` is SMALL or LARGE. `step` names the loop step, first in every error. `effort`
    ("low", "medium", "high") limits how much the model thinks first; Claude Haiku 4.5
    rejects it, so it is only for the large model.
    """
    model = os.environ[size]
    output_config = {"format": {"type": "json_schema", "schema": schema}}
    if effort:
        output_config["effort"] = effort
    with chat_span(model, system, prompt) as span:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config=output_config,
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        finish_chat_span(span, text, response.usage.input_tokens, response.usage.output_tokens)
    usage.record(step, model, response.usage.input_tokens, response.usage.output_tokens)
    if response.stop_reason != "end_turn":
        raise ModelError(f"{step}: model stopped with {response.stop_reason}")
    if not text:
        raise ModelError(f"{step}: model returned no text")
    return json.loads(text)
