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


def test_connectives_are_kept_only_when_factless_and_leading_into_a_claim():
    labels = label_passages([{"chunk_id": "a"}])
    kept = cited_sentences(
        [
            Sentence("Several laws matter here.", ()),
            Sentence("The directive applies from 2026.", ("P1",)),
            Sentence("Roughly 400 cities are covered.", ()),  # a number: a claim in disguise
            Sentence("Beyond deadlines, it also changes who acts.", ()),
            Sentence("Cities lead most measures.", ("P1",)),
            Sentence("That is the whole story.", ()),  # trailing: leads into nothing
        ],
        labels,
    )
    assert [s.text for s in kept] == [
        "Several laws matter here.",
        "The directive applies from 2026.",
        "Beyond deadlines, it also changes who acts.",
        "Cities lead most measures.",
    ]
    texts, _ = number_markers([kept])
    assert texts == [
        (
            "Several laws matter here. The directive applies from 2026 [1]. "
            "Beyond deadlines, it also changes who acts. Cities lead most measures [1]."
        )
    ]


def test_verification_counts_claims_only_and_drops_connectives_left_dangling():
    groups = [
        [
            Sentence("Intro.", ()),
            Sentence("A.", ("P1",)),
            Sentence("Then.", ()),
            Sentence("B.", ("P1",)),
        ],
        [Sentence("Lead-in.", ()), Sentence("C.", ("P2",))],
    ]
    # claims are A=0, B=1, C=2; B and C fail, so "Then." would lead into nothing
    assert drop_unsupported(groups, {0}) == [[Sentence("Intro.", ()), Sentence("A.", ("P1",))]]


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
        if tool == "coverage":
            return {"documents_matching_filters": 5}
        raise AssertionError(tool)


class FakeMemory:
    def __init__(self):
        self.saved = []

    def last_answer(self, session):
        return None

    def save_turn(self, session, question, answer):
        self.saved.append((session, question, answer))


DRAFT_EXTRAS = {"implications": [], "limits": [], "questions": []}
PROMPTS = []


def fake_models(monkeypatch, draft, supported, redraft=None):
    PROMPTS.clear()

    def ask_json(client, size, *, step, **kwargs):
        PROMPTS.append((step, kwargs))
        if step == "draft":
            return {**DRAFT_EXTRAS, **draft}
        if step == "redraft":
            return {**DRAFT_EXTRAS, **(redraft or draft)}
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
    rewrite = next(kwargs["prompt"] for step, kwargs in PROMPTS if step == "rewrite")
    assert "Heat-resilient cities" in rewrite  # searches in the words of what it already found


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
        "limits": ["No cost data."],
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


class FakeGuardrail:
    """Intervenes on any answer text containing 'diseases'."""

    def apply_guardrail(self, **request):
        answer = request["content"][2]["text"]["text"]
        return {"action": "GUARDRAIL_INTERVENED" if "diseases" in answer else "NONE"}


def test_grounding_check_drops_only_the_failing_paragraph(monkeypatch):
    draft = {
        "answerable": True,
        "paragraphs": [
            {"sentences": [{"text": "Cool roofs lowered surface heat.", "passages": ["P1"]}]},
            {"sentences": [{"text": "They also cured all diseases.", "passages": ["P1"]}]},
        ],
    }
    fake_models(monkeypatch, draft, {0, 1})
    settings = Settings(
        relevance_threshold=0.1,
        quick_rounds=2,
        deep_rounds=3,
        guardrail_id="g",
        guardrail_version="2",
    )
    agent = Agent(
        Deps(llm=None, gateway=FakeGateway(0.3), memory=None, bedrock=FakeGuardrail()), settings
    )
    events = list(agent.run({"question": "q"}))
    answer = events[-1]["answer"]
    assert answer["paragraphs"] == ["Cool roofs lowered surface heat [1]."]
    assert (answer["claimsTotal"], answer["claimsVerified"]) == (2, 1)
    verify = next(
        e for e in events if e["type"] == "step" and e["id"] == "verify" and e["status"] == "done"
    )
    assert verify["detail"] == "1 part removed by the grounding check"


def test_built_from_shows_a_single_year_once():
    assert built_from([{"docId": "a", "year": 2026}, {"docId": "b", "year": 2026}]) == (
        "Built from 2 WRI publications, 2026"
    )


def test_numbers_not_in_flags_figures_no_passage_gave():
    from askwri.agent.citations import numbers_not_in

    source = "In 2024, 181 of 394 cities missed the 1,000 limit."
    assert numbers_not_in("Focus on the 181 cities that missed it in 2024.", source) == []
    assert numbers_not_in("About 1000 cities, not 250, are affected.", source) == ["250"]


def test_answer_has_scope_audience_sections_and_drops_implications_with_new_numbers(monkeypatch):
    draft = {
        **DRAFT,
        "implications": ["Target cool roofs first.", "Fund 300 new parks."],
        "limits": ["No cost data."],
        "questions": ["What do cool roofs cost?"],
    }
    fake_models(monkeypatch, draft, {0})
    agent = Agent(Deps(llm=None, gateway=FakeGateway(0.3), memory=None, bedrock=None), SETTINGS)
    events = list(agent.run({"question": "q", "audience": "policymaker"}))
    answer = events[-1]["answer"]
    assert answer["audience"] == "policymaker"
    assert answer["scope"] == "Based on 1 of the 5 WRI publications indexed in AskWRI"
    assert answer["implications"] == ["Target cool roofs first."]  # "300" is in no passage
    assert (answer["limits"], answer["questions"]) == (
        ["No cost data."],
        ["What do cool roofs cost?"],
    )
    assert answer["removedClaims"] == ["They also cured all diseases."]
    system = next(kwargs["system"] for step, kwargs in PROMPTS if step == "draft")
    assert "Write for a policymaker" in system


def test_without_a_chosen_audience_the_drafter_infers_it_from_the_question(monkeypatch):
    fake_models(monkeypatch, {**DRAFT, "audience": "policymaker"}, {0})
    agent = Agent(Deps(llm=None, gateway=FakeGateway(0.3), memory=None, bedrock=None), SETTINGS)
    for request in [
        {"question": "Which laws should we target?"},
        {"question": "q", "audience": "x"},
    ]:
        PROMPTS.clear()
        answer = list(agent.run(request))[-1]["answer"]
        assert answer["audience"] == "policymaker"
        system = next(kwargs["system"] for step, kwargs in PROMPTS if step == "draft")
        assert "work it out from the question" in system


def test_most_claims_failing_triggers_one_stricter_redraft_and_keeps_the_better(monkeypatch):
    first = {
        "answerable": True,
        "paragraphs": [
            {
                "sentences": [
                    {"text": "Claim A.", "passages": ["P1"]},
                    {"text": "Claim B.", "passages": ["P1"]},
                    {"text": "Claim C.", "passages": ["P1"]},
                ]
            }
        ],
    }
    better = {
        "answerable": True,
        "paragraphs": [
            {
                "sentences": [
                    {"text": "Close claim one.", "passages": ["P1"]},
                    {"text": "Close claim two.", "passages": ["P1"]},
                ]
            }
        ],
    }
    fake_models(monkeypatch, first, {0}, redraft=better)  # first draft: 1 of 3 kept
    calls = []
    real = loop.llm.ask_json

    def counting(client, size, *, step, **kwargs):
        calls.append(step)
        # The redraft's verify step keeps both claims.
        if step == "verify" and calls.count("verify") == 2:
            return {"verdicts": [{"index": 0, "supported": True}, {"index": 1, "supported": True}]}
        return real(client, size, step=step, **kwargs)

    monkeypatch.setattr(loop.llm, "ask_json", counting)
    agent = Agent(Deps(llm=None, gateway=FakeGateway(0.3), memory=None, bedrock=None), SETTINGS)
    events = list(agent.run({"question": "q"}))
    answer = events[-1]["answer"]
    assert calls.count("redraft") == 1
    assert answer["paragraphs"] == ["Close claim one [1]. Close claim two [1]."]
    assert (answer["claimsTotal"], answer["claimsVerified"]) == (2, 2)
    redraft_prompt = next(kwargs["prompt"] for step, kwargs in PROMPTS if step == "redraft")
    assert "Claim B." in redraft_prompt and "staying close to their wording" in redraft_prompt
