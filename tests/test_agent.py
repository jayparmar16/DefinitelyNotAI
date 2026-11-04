import json
from datetime import datetime

import pytest

from askwri.agent import llm, loop
from askwri.agent.citations import (
    Sentence,
    cited_sentences,
    drop_unsupported,
    label_passages,
    number_markers,
    with_markers,
)
from askwri.agent.gateway import ToolError, parse_mcp_reply, tool_result
from askwri.agent.loop import Agent, Deps, Settings, built_from, search_arguments
from askwri.agent.memory import latest_answer

# --- citations ---


def test_markers_go_before_final_punctuation():
    assert with_markers("Buses ran on routes.", [1, 2]) == "Buses ran on routes [1][2]."
    assert with_markers("No full stop", [3]) == "No full stop [3]"


def test_markers_are_numbered_by_first_use_across_paragraphs():
    groups = [
        [Sentence("A.", ("P3",)), Sentence("B.", ("P1", "P3"))],
        [Sentence("C.", ("P2",))],
    ]
    texts, order = number_markers(groups)
    assert texts == ["A [1]. B [2][1].", "C [3]."]
    assert order == ["P3", "P1", "P2"]


def test_sentences_without_a_real_passage_are_dropped():
    labels = label_passages([{"chunk_id": "a"}, {"chunk_id": "b"}])
    kept = cited_sentences(
        [
            Sentence("Cited.", ("P1", "P9")),
            Sentence("Invented label.", ("P9",)),
            Sentence("No citation.", ()),
            Sentence("  ", ("P2",)),
        ],
        labels,
    )
    assert kept == [Sentence("Cited.", ("P1",))]


def test_unsupported_claims_are_dropped_and_empty_paragraphs_removed():
    groups = [[Sentence("A.", ("P1",)), Sentence("B.", ("P1",))], [Sentence("C.", ("P2",))]]
    assert drop_unsupported(groups, {0}) == [[Sentence("A.", ("P1",))]]
    assert drop_unsupported(groups, {1, 2}) == [
        [Sentence("B.", ("P1",))],
        [Sentence("C.", ("P2",))],
    ]


def test_built_from_counts_documents_and_year_span():
    sources = [
        {"docId": "a", "year": 2019},
        {"docId": "a", "year": 2019},
        {"docId": "b", "year": 2022},
    ]
    assert built_from(sources) == "Built from 2 WRI publications, 2019 to 2022"
    assert built_from([{"docId": "a", "year": None}]) == "Built from 1 WRI publication"


def test_search_arguments_map_ui_filters_to_tool_names():
    assert search_arguments("heat", "quick", {"yearFrom": 2010, "pubType": "Report"}) == {
        "query": "heat",
        "k": 8,
        "year_from": 2010,
        "pub_type": "Report",
    }
    assert search_arguments("heat", "deep", {}) == {"query": "heat", "k": 6}


# --- gateway replies and memory ---


def test_mcp_reply_parses_json_and_server_sent_events():
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"content": [{"type": "text", "text": '{"x": 1}'}]},
    }
    assert parse_mcp_reply(json.dumps(message)) == message
    assert parse_mcp_reply(f"event: message\ndata: {json.dumps(message)}\n\n") == message
    assert tool_result("search", message) == {"x": 1}


def test_tool_errors_raise_with_the_tool_name():
    with pytest.raises(ToolError, match="search: boom"):
        tool_result("search", {"result": {"isError": True, "content": [{"text": "boom"}]}})
    with pytest.raises(ToolError, match="coverage"):
        tool_result("coverage", {"error": {"message": "bad args"}})


def test_latest_answer_picks_the_newest_assistant_answer():
    def event(when, answer):
        text = json.dumps({"askwri_answer": answer})
        return {
            "eventTimestamp": datetime(2026, 11, 4, when),
            "payload": [
                {"conversational": {"role": "USER", "content": {"text": "q"}}},
                {"conversational": {"role": "ASSISTANT", "content": {"text": text}}},
            ],
        }

    assert latest_answer([event(9, {"n": 1}), event(11, {"n": 2}), event(10, {"n": 3})]) == {"n": 2}
    assert latest_answer([]) is None


# --- the loop, end to end with fakes ---

RESULT = {
    "chunk_id": "heat#p4-1",
    "doc_id": "heat",
    "title": "Heat-resilient cities",
    "url": None,
    "doi": None,
    "year": 2026,
    "date_confidence": "high",
    "pub_type": "Technical note",
    "office": None,
    "page": 6,
    "printed_page": "4",
    "section": "Findings",
    "kind": "source_text",
    "quotable": True,
    "passage": "Cool roofs lowered surface heat.",
    "relevance": 0.3,
    "why": {"by_meaning": True},
}


class FakeGateway:
    def __init__(self, relevance):
        self.relevance, self.calls = relevance, []

    def call(self, tool, arguments):
        self.calls.append(tool)
        if tool == "search":
            return {"results": [{**RESULT, "relevance": self.relevance}]}
        if tool == "authors":
            return {"documents": [{"doc_id": "heat", "authors": ["Ana Silva"]}], "people": []}
        raise AssertionError(tool)


class FakeMemory:
    def __init__(self):
        self.saved = []

    def last_answer(self, session):
        return None

    def save_turn(self, session, question, answer):
        self.saved.append((session, question, answer))


def fake_models(monkeypatch, draft, supported):
    def ask_json(client, size, *, step, **kwargs):
        if step == "draft":
            return draft
        if step == "verify":
            return {"verdicts": [{"index": i, "supported": i in supported} for i in range(10)]}
        if step == "rewrite":
            return {"query": "urban heat"}
        raise AssertionError(step)

    monkeypatch.setattr(llm, "ask_json", ask_json)


SETTINGS = Settings(
    relevance_threshold=0.1,
    quick_rounds=2,
    deep_rounds=3,
    guardrail_id=None,
    guardrail_version=None,
)
DRAFT = {
    "answerable": True,
    "paragraphs": [
        {
            "sentences": [
                {"text": "Cool roofs lowered surface heat.", "passages": ["P1"]},
                {"text": "They also cured all diseases.", "passages": ["P1"]},
            ]
        }
    ],
}


def run(monkeypatch, relevance, draft=DRAFT, supported=(0,)):
    fake_models(monkeypatch, draft, set(supported))
    memory = FakeMemory()
    agent = Agent(
        Deps(llm=None, gateway=FakeGateway(relevance), memory=memory, bedrock=None), SETTINGS
    )
    events = list(agent.run({"question": "How do cities cool down?", "sessionId": "s" * 40}))
    return events, memory


def test_quick_answer_keeps_only_verified_cited_claims(monkeypatch):
    events, memory = run(monkeypatch, relevance=0.3)
    answer = events[-1]["answer"]
    assert answer["paragraphs"] == ["Cool roofs lowered surface heat [1]."]
    assert (answer["claimsTotal"], answer["claimsVerified"]) == (2, 1)
    source = answer["sources"][0]
    assert (source["marker"], source["page"], source["printedPage"]) == (1, 6, "4")
    assert source["authors"] == ["Ana Silva"]
    assert memory.saved and memory.saved[0][2] == answer
    assert any(e["type"] == "source-found" for e in events)


def test_weak_evidence_retries_then_declines_with_what_was_searched(monkeypatch):
    events, memory = run(monkeypatch, relevance=0.01)
    final = events[-1]
    assert final["type"] == "decline"
    assert final["decline"]["searched"][:2] == ["How do cities cool down?", "urban heat"]
    assert final["decline"]["related"][0]["title"] == "Heat-resilient cities"
    assert not memory.saved


def test_answer_with_no_verified_claims_is_declined_not_shown(monkeypatch):
    events, _ = run(monkeypatch, relevance=0.3, supported=())
    assert events[-1]["type"] == "decline"
    assert "could not verify" in events[-1]["decline"]["message"]


def test_unanswerable_draft_is_declined(monkeypatch):
    events, _ = run(monkeypatch, relevance=0.3, draft={"answerable": False, "paragraphs": []})
    assert events[-1]["type"] == "decline"


def test_every_step_that_starts_also_finishes(monkeypatch):
    events, _ = run(monkeypatch, relevance=0.3)
    steps = [e for e in events if e["type"] == "step"]
    started = {e["id"] for e in steps if e["status"] == "now"}
    done = {e["id"] for e in steps if e["status"] == "done"}
    assert started == done
    assert loop.PASSAGES["quick"] >= 1


class TranslatingGateway(FakeGateway):
    def call(self, tool, arguments):
        if tool == "translate":
            return {"translation": f"ES: {arguments['text']}", "numbers_preserved": True}
        return super().call(tool, arguments)


def test_a_translated_report_translates_its_title_and_gaps_too(monkeypatch):
    draft = {
        "answerable": True,
        "title": "Cooling cities",
        "thin_evidence": ["No cost data."],
        "key_points": [{"text": "Cool roofs lowered surface heat.", "passages": ["P1"]}],
    }
    monkeypatch.setattr(
        loop.Agent, "_plan", lambda self, q, m: iter_return([{"question": q, "search_query": q}])
    )
    fake_models(monkeypatch, draft, {0})
    agent = Agent(
        Deps(llm=None, gateway=TranslatingGateway(0.3), memory=None, bedrock=None), SETTINGS
    )
    answer = list(agent.run({"question": "q", "mode": "deep", "language": "es"}))[-1]["answer"]
    report = answer["report"]
    assert answer["machineTranslated"] and answer["language"] == "es"
    assert report["title"] == "ES: Cooling cities"
    assert report["thinEvidence"] == ["ES: No cost data."]
    assert (
        report["keyPoints"] == answer["paragraphs"] == ["ES: Cool roofs lowered surface heat [1]."]
    )


def iter_return(value):
    """A generator that yields nothing and returns value (stands in for a loop step)."""
    return value
    yield
