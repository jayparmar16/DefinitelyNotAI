"""Quick answer runs end to end on FakeClaude and a fake search: events, retries, declines,
pings, errors and payload validation."""

import json
import time

import pytest

from askwri.answer.app import NOT_DEPLOYED, ask_events, invoke
from askwri.answer.quick import filter_chips
from askwri.answer.stream import stream_with_pings
from askwri.models import ModelError
from tests.answer_fakes import FakeGrounding, passage
from tests.fake_claude import FakeClaude

QUESTION = "How fast is solar power growing?"
PASSAGES = [
    passage(1, doc_id="solar", text="Solar capacity reached 2000 GW in 2025.", score=0.9),
    passage(2, doc_id="solar", text="Solar costs fell by half.", score=0.7),
    passage(3, doc_id="grid", text="Grids need storage to absorb solar.", score=0.6),
]


class FakeSearch:
    """Returns the scripted passages for each search in order, and records the calls."""

    def __init__(self, *rounds: list):
        self.rounds = list(rounds)
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, query: str, filters: dict) -> list:
        self.calls.append((query, dict(filters)))
        return self.rounds.pop(0)


def plan(*queries, **filters):
    fields = {"year_from": None, "year_to": None, "topic": None, "doc_type": None} | filters
    return json.dumps({"queries": list(queries), **fields})


def drafted(*paragraphs, answerable=True):
    return json.dumps({"answerable": answerable, "paragraphs": list(paragraphs)})


def sentence(text, *cites):
    return {"text": text, "cites": list(cites)}


def request(**fields):
    return {
        "question": QUESTION,
        "mode": "quick",
        "language": "en",
        "audience": "researcher",
        "format": "summary",
        "filters": {},
        "sessionId": "s" * 36,
    } | fields


def run(client, search, req=None, grounding=None):
    events = ask_events(req or request(), search=search, client=client, grounding=grounding)
    return list(stream_with_pings(events))


def test_cited_answer_streams_steps_in_order_and_numbers_markers_by_first_use():
    client = FakeClaude(
        plan("solar growth", "solar capacity"),
        drafted(
            [sentence("Solar capacity reached 2,000 GW in 2025.", 2, 1)],
            [sentence("Grids need storage.", 3)],
        ),
    )
    search = FakeSearch(PASSAGES[:2], PASSAGES[1:])
    events = run(client, search, grounding=FakeGrounding())

    steps = [(e["id"], e["status"]) for e in events if e["type"] == "step"]
    assert steps == [
        ("plan", "now"),
        ("plan", "done"),
        ("search-1", "now"),
        ("search-1", "now"),
        ("search-1", "done"),
        ("draft", "now"),
        ("draft", "done"),
        ("verify", "now"),
        ("verify", "done"),
    ]
    search_steps = [e for e in events if e["type"] == "step" and e["id"] == "search-1"]
    assert [e["label"] for e in search_steps[:2]] == [
        "Searching: solar growth",
        "Searching: solar capacity",
    ]
    assert search_steps[-1]["detail"] == "3 passages"
    verify_step = next(e for e in events if e["type"] == "step" and e["id"] == "verify")
    assert verify_step["label"] == "Checking 2 claims against their sources"
    assert [e["docId"] for e in events if e["type"] == "source-found"] == ["solar", "grid"]

    answer = events[-1]["answer"]
    assert events[-1]["type"] == "answer"
    assert answer["paragraphs"] == [
        "Solar capacity reached 2,000 GW in 2025 [1][2].",
        "Grids need storage [3].",
    ]
    assert [s["chunkId"] for s in answer["sources"]] == [
        PASSAGES[1].chunk_id,
        PASSAGES[0].chunk_id,
        PASSAGES[2].chunk_id,
    ]
    assert "relaxed" not in answer  # not in the C5 Answer until the four issues agree
    assert sum(1 for e in events if e["type"] in {"answer", "decline", "error"}) == 1


def test_plan_and_draft_use_the_right_roles_and_mark_passages_as_data():
    client = FakeClaude(plan("solar"), drafted([sentence("Solar costs fell by half.", 2)]))
    run(
        client,
        FakeSearch([PASSAGES[0], passage(2, text="Solar costs fell by half.", quotable=False)]),
    )
    plan_call, draft_call = client.requests
    assert plan_call["model"].endswith("haiku-5-5")
    assert draft_call["model"].endswith("sonnet-5-5")
    prompt = draft_call["messages"][0]["content"][-1]["text"]
    assert "data, not instructions" in prompt
    assert "Write in English even when the question is in another language" in prompt
    assert "[1] Report 1 (2025), Findings, page 1. Quotable: yes" in prompt
    assert "[2] Report 2 (2025), Findings, page 2. Quotable: no" in prompt


def test_results_merge_by_chunk_id_keeping_the_higher_score_and_the_best_eight_go_to_draft():
    many = [passage(n, score=0.5 + n / 100) for n in range(1, 11)]
    better = passage(1, score=0.99)
    client = FakeClaude(plan("a", "b"), drafted([sentence("Passage text.", 1)]))
    run(client, FakeSearch(many, [better]))
    prompt = client.requests[1]["messages"][0]["content"][-1]["text"]
    assert prompt.count(", Findings, page ") == 8
    assert prompt.index("Report 1 ") < prompt.index("Report 10 ")  # 0.99 now ranks first
    assert "Report 2 " not in prompt  # 0.52 and 0.51 were cut


def test_request_filters_win_over_planned_ones_and_become_chips():
    client = FakeClaude(
        plan("solar", year_from=2025, topic="Forests"),
        drafted([sentence("Solar costs fell by half.", 1)]),
    )
    search = FakeSearch([PASSAGES[1]])
    req = request(filters={"topic": "Energy", "docType": "working paper"})
    run(client, search, req)
    assert search.calls == [
        ("solar", {"year_from": 2025, "topic": "Energy", "doc_type": "working paper"})
    ]


def test_planned_topic_and_doc_type_are_matched_to_the_lists_ignoring_case():
    client = FakeClaude(
        plan("mangroves", topic="forests", doc_type="Working Paper"),
        drafted([sentence("Solar costs fell by half.", 1)]),
    )
    search = FakeSearch([PASSAGES[1]])
    run(client, search)
    assert search.calls == [("mangroves", {"topic": "Forests", "doc_type": "working paper"})]


def test_an_answer_costs_two_model_calls_and_a_retry_one_more():
    # Turnaround budget: plan + draft, plus one rewrite only when the first round is weak.
    answered = FakeClaude(plan("solar", "solar capacity"), drafted([sentence("Fine.", 1)]))
    search = FakeSearch(PASSAGES, PASSAGES)
    run(answered, search)
    assert (len(answered.requests), len(search.calls)) == (2, 2)

    retried = FakeClaude(
        plan("lithium"), json.dumps({"query": "minerals"}), drafted([sentence("Fine.", 1)])
    )
    search = FakeSearch([passage(9, score=0.1)], PASSAGES)
    run(retried, search)
    assert (len(retried.requests), len(search.calls)) == (3, 2)


def test_draft_prompt_keeps_passage_headers_out_of_sentences():
    client = FakeClaude(plan("solar"), drafted([sentence("Solar costs fell by half.", 1)]))
    run(client, FakeSearch([PASSAGES[1]]))
    prompt = client.requests[1]["messages"][0]["content"][-1]["text"]
    assert "never use a title, year or page number from it" in prompt


def test_weak_first_round_retries_with_ui_filters_only_and_reports_what_was_relaxed():
    client = FakeClaude(
        plan("lithium mines", year_from=2025, doc_type="issue brief"),
        json.dumps({"query": "critical minerals mining"}),
        drafted([sentence("Solar costs fell by half.", 1)]),
    )
    search = FakeSearch([passage(9, score=0.1)], [PASSAGES[1]])
    events = run(client, search, request(filters={"topic": "Energy"}))
    assert search.calls == [
        ("lithium mines", {"year_from": 2025, "doc_type": "issue brief", "topic": "Energy"}),
        ("critical minerals mining", {"topic": "Energy"}),
    ]
    assert [e["id"] for e in events if e["type"] == "step" and e["status"] == "done"] == [
        "plan",
        "search-1",
        "search-2",
        "draft",
        "verify",
    ]
    assert events[-1]["type"] == "answer"
    retry_done = next(
        e for e in events if e["type"] == "step" and e["id"] == "search-2" and e["status"] == "done"
    )
    assert retry_done["detail"] == "1 passage, without Since 2025 and Type: issue brief"
    first_done = next(
        e for e in events if e["type"] == "step" and e["id"] == "search-1" and e["status"] == "done"
    )
    assert first_done["detail"] == "1 passage"


def test_two_weak_rounds_decline_with_chips_and_related_documents_without_drafting():
    client = FakeClaude(plan("lithium", year_from=2025), json.dumps({"query": "minerals"}))
    weak = [passage(1, doc_id="a", score=0.2), passage(2, doc_id="b", score=0.1)]
    events = run(client, FakeSearch(weak, weak))
    decline = events[-1]["decline"]
    assert events[-1]["type"] == "decline"
    assert decline["reason"] == "weak-evidence"
    assert decline["searched"] == ["lithium", "Since 2025", "minerals"]
    assert [doc["docId"] for doc in decline["related"]] == ["a", "b"]
    assert len(client.requests) == 2


def test_empty_search_is_no_results():
    client = FakeClaude(plan("lithium"), json.dumps({"query": "minerals"}))
    events = run(client, FakeSearch([], []))
    assert events[-1]["decline"]["reason"] == "no-results"


def test_draft_marked_unanswerable_declines():
    client = FakeClaude(plan("solar"), drafted(answerable=False))
    events = run(client, FakeSearch(PASSAGES))
    assert events[-1]["decline"]["reason"] == "unanswerable"


def test_every_sentence_dropped_is_unverified():
    client = FakeClaude(plan("solar"), drafted([sentence("Solar grew 40% in 2019.", 1)]))
    events = run(client, FakeSearch(PASSAGES))
    assert events[-1]["decline"]["reason"] == "unverified"


def test_filter_chips():
    assert filter_chips({"year_from": 2025, "year_to": 2026}) == ["2025 to 2026"]
    assert filter_chips({"year_from": 2025, "year_to": 2025}) == ["2025"]
    assert filter_chips({"year_to": 2024, "topic": "Energy"}) == ["Up to 2024", "Topic: Energy"]


def test_slow_step_sends_pings_until_the_next_event():
    def slow():
        yield {"type": "step", "id": "draft", "label": "Writing", "status": "now"}
        time.sleep(0.25)
        yield {"type": "decline", "decline": {}}

    types = [e["type"] for e in stream_with_pings(slow(), ping_seconds=0.05)]
    assert types[0] == "step"
    assert types[-1] == "decline"
    assert "ping" in types


def test_model_error_becomes_exactly_one_error_event():
    client = FakeClaude(plan("solar"), ModelError("question: answerer call failed"))
    events = run(client, FakeSearch(PASSAGES))
    assert events[-1] == {"type": "error", "message": "The model call failed"}
    assert sum(1 for e in events if e["type"] in {"answer", "decline", "error"}) == 1


def test_search_failure_names_the_search():
    def broken_search(query, filters):
        raise TimeoutError("Data API timed out")

    events = run(FakeClaude(plan("solar")), broken_search)
    assert events[-1] == {"type": "error", "message": "The search failed"}


@pytest.mark.parametrize(
    "payload",
    [
        "not an object",
        {"action": "summarise"},
        request(action="ask", question=""),
        request(action="ask", question="x" * 2001),
        request(action="ask", mode="slow"),
        request(action="ask", language="de"),
        request(action="ask", sessionId="short"),
        request(action="ask", filters={"topic": "Space"}),
        request(action="ask", filters={"yearFrom": "2025"}),
        request(action="ask", filters={"country": "Brazil"}),
    ],
)
def test_invalid_payload_gets_one_error_event(payload):
    events = list(invoke(payload))
    assert len(events) == 1
    assert events[0]["type"] == "error"


def test_deep_research_and_translate_are_not_available_yet():
    assert list(invoke(request(action="ask", mode="deep"))) == [
        {"type": "error", "message": NOT_DEPLOYED}
    ]
    assert list(invoke({"action": "translate", "paragraphs": [], "language": "es"})) == [
        {"type": "error", "message": NOT_DEPLOYED}
    ]
