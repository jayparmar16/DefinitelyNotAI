import pytest

from askwri.api.server import BadRequest, chat_payload, download_key, key_matches


def test_chat_payload_keeps_valid_fields_and_defaults_the_rest():
    payload = chat_payload(
        {
            "question": "  How do cities cool down?  ",
            "mode": "deep",
            "language": "es",
            "format": "issue-brief",
            "filters": {"yearFrom": 2010, "evil": "x"},
            "sessionId": "a" * 36,
        }
    )
    assert payload["question"] == "How do cities cool down?"
    assert (payload["mode"], payload["format"], payload["language"]) == (
        "deep",
        "issue-brief",
        "es",
    )
    assert payload["filters"] == {"yearFrom": 2010}
    assert payload["sessionId"] == "a" * 36


def test_unknown_mode_and_short_session_are_replaced_not_trusted():
    payload = chat_payload({"question": "q", "mode": "admin", "sessionId": "short"})
    assert payload["mode"] == "quick"
    assert payload["sessionId"].startswith("askwri-") and len(payload["sessionId"]) >= 33


def test_empty_or_huge_questions_are_rejected():
    with pytest.raises(BadRequest):
        chat_payload({"question": "   "})
    with pytest.raises(BadRequest):
        chat_payload({"question": "x" * 4001})


def test_download_key_only_allows_stored_pdfs():
    assert download_key("key=raw/heat-report.pdf") == "raw/heat-report.pdf"
    for bad in [
        "key=eval/testset.jsonl",
        "key=raw/../secret.pdf",
        "key=raw/a/b.pdf",
        "",
        "key=raw/x.txt",
    ]:
        with pytest.raises(BadRequest):
            download_key(bad)


def test_api_key_is_required_only_when_configured():
    assert key_matches(None, None)
    assert key_matches("k1", "k1")
    assert not key_matches("k1", None)
    assert not key_matches("k1", "k2")
