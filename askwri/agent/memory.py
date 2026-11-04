"""Short-term conversation memory in AgentCore Memory (ASKWRI_MEMORY_ID).

Each turn stores the question and the final answer, so a follow-up such as "now in Spanish"
reuses the gathered evidence instead of searching again.
"""

import json
import os
from datetime import UTC, datetime

import boto3

ACTOR = "askwri-user"  # shortcut: one actor until the UI signs users in
ANSWER_KEY = "askwri_answer"


class Memory:
    """Read and write one session's turns."""

    def __init__(self, client=None):
        self._client = client or boto3.client("bedrock-agentcore")
        self._memory_id = os.environ["ASKWRI_MEMORY_ID"]

    def save_turn(self, session_id: str, question: str, answer: dict) -> None:
        """Store the question and the answer the user was shown."""
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
                        "content": {"text": json.dumps({ANSWER_KEY: answer}, ensure_ascii=False)},
                    }
                },
            ],
        )

    def last_answer(self, session_id: str) -> dict | None:
        """The most recent answer in this session, or None for a new session."""
        events = self._client.list_events(
            memoryId=self._memory_id,
            actorId=ACTOR,
            sessionId=session_id,
            includePayloads=True,
            maxResults=20,
        )["events"]
        return latest_answer(events)


def latest_answer(events: list[dict]) -> dict | None:
    """Find the newest stored answer among memory events (any order)."""
    newest, newest_time = None, None
    for event in events:
        for item in event.get("payload", []):
            content = item.get("conversational", {})
            if content.get("role") != "ASSISTANT":
                continue
            text = content.get("content", {}).get("text", "")
            if not text.startswith("{"):
                continue
            answer = json.loads(text).get(ANSWER_KEY)
            when = event["eventTimestamp"]
            if answer is not None and (newest_time is None or when > newest_time):
                newest, newest_time = answer, when
    return newest
