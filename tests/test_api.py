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


def test_warm_up_needs_a_valid_session_id():
    from askwri.api.server import warm_session

    assert warm_session({"sessionId": "s" * 36}) == "s" * 36
    for bad in [{}, {"sessionId": "short"}, {"sessionId": "x" * 36 + "/../"}]:
        with pytest.raises(BadRequest):
            warm_session(bad)


def test_a_reused_connection_survives_an_early_answer_with_an_unread_body():
    """An early 401 or 404 must still consume the request body, or the leftover bytes are
    parsed as the start of the next request on the same keep-alive connection."""
    import http.client
    import threading
    from http.server import ThreadingHTTPServer

    from askwri.api.server import Handler

    class FakeApi:
        origins = frozenset({"http://localhost:3000"})
        api_key = "k1"

    Handler.api = FakeApi()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        body = '{"sessionId": "' + "s" * 36 + '"}'
        connection.request(
            "POST", "/nowhere", body=body, headers={"Content-Type": "application/json"}
        )
        unknown = connection.getresponse()
        unknown.read()
        assert unknown.status == 404  # answered before any route looked at the body
        connection.request("POST", "/warm", body=body, headers={"Content-Type": "application/json"})
        first = connection.getresponse()
        first.read()
        assert first.status == 401  # no key: answered before the route read the body
        connection.request("OPTIONS", "/chat", headers={"Origin": "http://localhost:3000"})
        second = connection.getresponse()
        second.read()
        assert second.status == 204
    finally:
        server.shutdown()
