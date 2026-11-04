"""The decline rule: when to refuse to answer, and the decline event that says what was searched."""

import os

MESSAGES = {
    "no-results": "I couldn't find any WRI publications on this. Here is what I searched.",
    "weak-evidence": (
        "WRI's publications in AskWRI don't seem to address this directly. "
        "These are the closest matches I found."
    ),
    "unanswerable": (
        "The passages I found touch on this topic but don't answer your question. "
        "You may find these related publications useful."
    ),
    "unverified": (
        "I found related material but couldn't back up an answer with citations, "
        "so I'm not giving one. These publications are the best place to look."
    ),
}
MAX_RELATED = 3


def decline_score() -> float:
    """The rerank score a passage needs to count as evidence (`ASKWRI_DECLINE_SCORE`, 0.3)."""
    return float(os.environ.get("ASKWRI_DECLINE_SCORE", "0.3"))


def decline_reason(draft: dict, verification: dict) -> str | None:
    """The first reason the draft must be declined, or None when it can be answered.

    `verification` is what `verify` returned for this draft. Fewer than half of the claims
    surviving is a decline; exactly half is not.
    """
    if not draft["seen"]:
        return "no-results"
    if max(p.score for p in draft["seen"]) < decline_score():
        return "weak-evidence"
    if not draft["answerable"]:
        return "unanswerable"
    verified, total = verification["claims_verified"], verification["claims_total"]
    if verified == 0 or verified * 2 < total:
        return "unverified"
    return None


def decline_event(reason: str, draft: dict) -> dict:
    """The C5 `decline` event: a fixed message, the search chips and up to 3 related documents."""
    return {
        "type": "decline",
        "decline": {
            "reason": reason,
            "message": MESSAGES[reason],
            "searched": draft["searched"],
            "related": _related(draft["seen"]),
        },
    }


def _related(seen: list) -> list[dict]:
    best_first = {}
    for p in sorted(seen, key=lambda p: p.score, reverse=True):
        best_first.setdefault(p.doc_id, p)
    return [
        {
            "docId": p.doc_id,
            "title": p.doc_title,
            "docType": p.doc_type,
            "year": p.year,
            "url": p.link,
        }
        for p in list(best_first.values())[:MAX_RELATED]
    ]
