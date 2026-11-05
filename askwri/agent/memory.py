"""Short-term conversation memory in AgentCore Memory (ASKWRI_MEMORY_ID).

Each turn stores the question (as the agent read it) and the final answer, so a follow-up can
be read in context, and "now in Spanish" or "make it shorter" reuse the gathered evidence.
"""

import json
import os
from datetime import UTC, datetime

import boto3

ACTOR = "askwri-user"  # shortcut: one actor until the UI signs users in
ANSWER_KEY = "askwri_answer"
# AgentCore Memory takes at most 100,000 characters per message; a topic dossier's answer (8
# papers through a lens, with every source passage) can be larger.
MAX_STORED = 95_000
PASSAGE_CHARS = 1_200


def stored_text(answer: dict) -> str:
    """The answer as stored for follow-ups, made to fit one memory message: first the source
    passages are shortened, then the lens and dossier tables are left out (a follow-up then
    redrafts or translates the answer without them), then the later sources."""
    text = json.dumps({ANSWER_KEY: answer}, ensure_ascii=False)
    if len(text) <= MAX_STORED:
        return text
    sources = [{**s, "passage": s["passage"][:PASSAGE_CHARS]} for s in answer.get("sources", [])]
    answer = {**answer, "sources": sources}
    text = json.dumps({ANSWER_KEY: answer}, ensure_ascii=False)
    if len(text) <= MAX_STORED:
        return text
    answer = {k: v for k, v in answer.items() if k not in ("lens", "dossier")}
    text = json.dumps({ANSWER_KEY: answer}, ensure_ascii=False)
    # Still too large: keep the first sources (the answer cites them in order) until it fits.
    while len(text) > MAX_STORED and len(answer["sources"]) > 1:
        answer = {**answer, "sources": answer["sources"][: len(answer["sources"]) // 2]}
        text = json.dumps({ANSWER_KEY: answer}, ensure_ascii=False)
    return text


class Memory:
    """Read and write one session's turns."""

    def __init__(self, client=None):
        self._client = client or boto3.client("bedrock-agentcore")
        self._memory_id = os.environ["ASKWRI_MEMORY_ID"]

    def save_turn(self, session_id: str, question: str, answer: dict) -> None:
        """Store the question and the answer in English, before any translation the user saw."""
        self._client.create_event(
            memoryId=self._memory_id,
            actorId=ACTOR,
            sessionId=session_id,
            eventTimestamp=datetime.now(UTC),
            payload=[
                {"conversational": {"role": "USER", "content": {"text": question}}},
                {
                    "conversational": {
                        "role": "ASSISTANT",
                        "content": {"text": stored_text(answer)},
                    }
                },
            ],
        )

    def last_turn(self, session_id: str) -> dict | None:
        """The most recent {"question", "answer"} in this session, or None for a new session."""
        events = self._client.list_events(
            memoryId=self._memory_id,
            actorId=ACTOR,
            sessionId=session_id,
            includePayloads=True,
            maxResults=20,
        )["events"]
        return latest_turn(events)


def latest_turn(events: list[dict]) -> dict | None:
    """Find the newest stored question and answer among memory events (any order)."""
    newest, newest_time = None, None
    for event in events:
        question, answer = "", None
        for item in event.get("payload", []):
            content = item.get("conversational", {})
            text = content.get("content", {}).get("text", "")
            if content.get("role") == "USER":
                question = text
            elif content.get("role") == "ASSISTANT" and text.startswith("{"):
                answer = json.loads(text).get(ANSWER_KEY)
        when = event["eventTimestamp"]
        if answer is not None and (newest_time is None or when > newest_time):
            newest, newest_time = {"question": question, "answer": answer}, when
    return newest
