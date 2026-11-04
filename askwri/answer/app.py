"""AgentCore Runtime entrypoint (C3): validate an ask payload and stream the answer as SSE events.

Run locally with `uv run python askwri/answer/app.py`; it serves POST /invocations on port 8080.
"""

import sys
from pathlib import Path

# AgentCore and the local command run this file as a script, which puts only askwri/answer on
# the import path; the repo root is needed to import the askwri package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import logging
import time
from collections.abc import Iterator

from bedrock_agentcore import BedrockAgentCoreApp

from askwri.answer.finalize import respond
from askwri.answer.quick import Search, index_search, quick_draft
from askwri.answer.stream import stream_with_pings
from askwri.answer.verify import Grounding, guardrail_grounding
from askwri.ingest.model_labels import DOC_TYPE_NAMES, TOPICS
from askwri.models import claude_client

MODES = ("quick", "deep")
LANGUAGES = ("en", "es", "pt", "fr", "hi", "id")
AUDIENCES = ("researcher", "policymaker", "partnerships")
FORMATS = ("summary", "issue-brief", "talking-points")
MAX_QUESTION_CHARS = 2000
SESSION_ID_CHARS = (33, 100)
NOT_DEPLOYED = "Deep research is not available in this deployment"

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload) -> Iterator[dict]:
    """Stream the C5 events for one `ask` payload; any other payload gets one `error` event."""
    problem = payload_problem(payload)
    if problem:
        return _error(problem)
    if payload["mode"] == "deep":
        return _error(NOT_DEPLOYED)
    request = {key: value for key, value in payload.items() if key != "action"}
    events = ask_events(
        request, search=index_search, client=claude_client(), grounding=guardrail_grounding()
    )
    return stream_with_pings(events)


def _error(message: str) -> Iterator[dict]:
    # A generator, not a list: AgentCore streams SSE only when the entrypoint returns one.
    yield {"type": "error", "message": message}


def ask_events(
    request: dict, *, search: Search, client, grounding: Grounding | None
) -> Iterator[dict]:
    """The Quick answer run: draft, verify, then end with one `answer` or `decline` event."""
    started_at = time.monotonic()
    draft = yield from quick_draft(request, search=search, client=client)
    claims = sum(len(paragraph) for paragraph in draft["paragraphs"])
    label = f"Checking {claims} claim{'' if claims == 1 else 's'} against their sources"
    if claims:
        yield {"type": "step", "id": "verify", "label": label, "status": "now"}
    result = respond(draft, request, grounding=grounding, started_at=started_at)
    if claims:
        yield {"type": "step", "id": "verify", "label": label, "status": "done"}
    yield result


def payload_problem(payload) -> str | None:
    """Why the payload can't be answered, as the message for its `error` event, or None."""
    if not isinstance(payload, dict):
        return "The request must be a JSON object"
    if payload.get("action") == "translate":
        return NOT_DEPLOYED
    if payload.get("action") != "ask":
        return 'The action must be "ask" or "translate"'
    for key, allowed in (
        ("mode", MODES),
        ("language", LANGUAGES),
        ("audience", AUDIENCES),
        ("format", FORMATS),
    ):
        if payload.get(key) not in allowed:
            return f"{key} must be one of: {', '.join(allowed)}"
    question = payload.get("question")
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= MAX_QUESTION_CHARS:
        return f"The question must be 1 to {MAX_QUESTION_CHARS:,} characters"
    session_id = payload.get("sessionId")
    low, high = SESSION_ID_CHARS
    if not isinstance(session_id, str) or not low <= len(session_id) <= high:
        return f"sessionId must be {low} to {high} characters"
    return filters_problem(payload.get("filters", {}))


def filters_problem(filters) -> str | None:
    """Why the C5 filters are invalid, or None."""
    if not isinstance(filters, dict):
        return "filters must be an object"
    unknown = set(filters) - {"yearFrom", "yearTo", "topic", "docType"}
    if unknown:
        return f"Unknown filter: {', '.join(sorted(unknown))}"
    for key in ("yearFrom", "yearTo"):
        year = filters.get(key)
        if year is not None and (type(year) is not int or not 1900 <= year <= 2100):
            return f"{key} must be a year"
    if (
        filters.get("yearFrom")
        and filters.get("yearTo")
        and filters["yearFrom"] > filters["yearTo"]
    ):
        return "yearFrom must not be after yearTo"
    if filters.get("topic") not in (None, *TOPICS):
        return f"topic must be one of: {', '.join(TOPICS)}"
    if filters.get("docType") not in (None, *DOC_TYPE_NAMES):
        return f"docType must be one of: {', '.join(DOC_TYPE_NAMES)}"
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run()
