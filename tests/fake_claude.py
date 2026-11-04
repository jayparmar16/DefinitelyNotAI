"""A stand-in for the Anthropic client, so tests never call Bedrock."""

import json
from types import SimpleNamespace

# A reply to the enrichment request (model_labels.enrichment_from_text) that adds nothing.
NO_ENRICHMENT = json.dumps(
    {
        "topics": [],
        "concepts": [],
        "keywords": [],
        "countries": [],
        "regions": [],
        "key_findings": [],
        "genre": "other",
        "coverage": "",
    }
)


class FakeClaude:
    """Replays canned replies from `messages.create` and records the requests it received.

    Each reply is either text (a normal finished reply), an exception to raise, or a dict of
    response fields (for example `{"stop_reason": "refusal"}`) merged over a normal reply.
    """

    def __init__(self, *replies: str | Exception | dict):
        self.replies = list(replies)
        self.requests: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **request):
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, str):
            reply = {"content": [SimpleNamespace(type="text", text=reply)]}
        fields = {"stop_reason": "end_turn", "stop_details": None, "content": []} | reply
        return SimpleNamespace(**fields)
