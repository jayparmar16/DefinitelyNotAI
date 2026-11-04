"""The decline rule: which reason applies first, and what the decline event lists."""

from askwri.answer.decline import MESSAGES, decline_event, decline_reason
from tests.answer_fakes import passage

ANSWERED = {"claims_total": 4, "claims_verified": 4}


def draft(seen, answerable=True):
    return {"answerable": answerable, "seen": seen, "searched": ["solar", "2025 to 2026"]}


def test_no_passages_seen_is_no_results():
    assert decline_reason(draft([]), ANSWERED) == "no-results"


def test_no_passage_at_the_decline_score_is_weak_evidence(monkeypatch):
    seen = [passage(1, score=0.29), passage(2, score=0.1)]
    assert decline_reason(draft(seen), ANSWERED) == "weak-evidence"
    assert decline_reason(draft([passage(1, score=0.3)]), ANSWERED) is None
    monkeypatch.setenv("ASKWRI_DECLINE_SCORE", "0.5")
    assert decline_reason(draft([passage(1, score=0.4)]), ANSWERED) == "weak-evidence"


def test_draft_marked_unanswerable_is_unanswerable():
    assert decline_reason(draft([passage(1)], answerable=False), ANSWERED) == "unanswerable"


def test_fewer_than_half_verified_is_unverified_but_exactly_half_is_answered():
    seen = [passage(1)]
    assert decline_reason(draft(seen), {"claims_total": 4, "claims_verified": 0}) == "unverified"
    assert decline_reason(draft(seen), {"claims_total": 5, "claims_verified": 2}) == "unverified"
    assert decline_reason(draft(seen), {"claims_total": 4, "claims_verified": 2}) is None


def test_first_reason_that_applies_wins():
    weak_and_unanswerable = draft([passage(1, score=0.1)], answerable=False)
    assert decline_reason(weak_and_unanswerable, ANSWERED) == "weak-evidence"


def test_decline_event_lists_three_distinct_documents_best_score_first():
    seen = [
        passage(1, doc_id="a", score=0.2),
        passage(2, doc_id="b", score=0.6),
        passage(3, doc_id="a", score=0.9),
        passage(4, doc_id="c", score=0.4),
        passage(5, doc_id="d", score=0.1),
    ]
    event = decline_event("weak-evidence", draft(seen))
    decline = event["decline"]
    assert event["type"] == "decline"
    assert decline["message"] == MESSAGES["weak-evidence"]
    assert decline["searched"] == ["solar", "2025 to 2026"]
    assert [doc["docId"] for doc in decline["related"]] == ["a", "b", "c"]
    assert decline["related"][0] == {
        "docId": "a",
        "title": "Report 3",
        "docType": "research report",
        "year": 2025,
        "url": "https://www.wri.org/research/report-3",
    }


def test_every_reason_has_its_own_message():
    assert len(set(MESSAGES.values())) == 4
