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
from askwri.agent.memory import latest_turn

# --- citations ---


def test_markers_go_before_final_punctuation():
    assert with_markers("Buses ran on routes.", [1, 2]) == "Buses ran on routes [1][2]."
    assert with_markers("No full stop", [3]) == "No full stop [3]"


def test_every_sentence_of_a_claim_that_states_a_figure_carries_the_markers():
    point = "Cities drive 70 percent of GDP. Yet water is scarce. Costs reach $66 billion."
    assert with_markers(point, [1, 2]) == (
        "Cities drive 70 percent of GDP [1][2]. Yet water is scarce. Costs reach $66 billion [1][2]."
    )
    # Abbreviations are not sentence ends.
    assert with_markers("U.S. cities cut 20 percent. Others did too.", [3]) == (
        "U.S. cities cut 20 percent [3]. Others did too [3]."
    )
    assert with_markers("See e.g. 2019 data.", [1]) == "See e.g. 2019 data [1]."


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


def test_latest_turn_picks_the_newest_question_and_answer():
    def event(when, answer):
        text = json.dumps({"askwri_answer": answer})
        return {
            "eventTimestamp": datetime(2026, 11, 4, when),
            "payload": [
                {"conversational": {"role": "USER", "content": {"text": f"q{when}"}}},
                {"conversational": {"role": "ASSISTANT", "content": {"text": text}}},
            ],
        }

    events = [event(9, {"n": 1}), event(11, {"n": 2}), event(10, {"n": 3})]
    assert latest_turn(events) == {"question": "q11", "answer": {"n": 2}}
    assert latest_turn([]) is None


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
        if tool == "links":
            return {"links": [], "cited_by": {"heat": 2}}
        raise AssertionError(tool)


class FakeMemory:
    def __init__(self, previous=None):
        self.saved, self.previous = [], previous

    def last_turn(self, session):
        return self.previous

    def save_turn(self, session, question, answer):
        self.saved.append((session, question, answer))


SUMMARY = {"summary": [{"text": "In short, roofs cool cities.", "passages": ["P1"]}]}
DRAFT_EXTRAS = {
    "implications": [],
    "limits": [],
    "questions": [],
    "question_language": "en",
    "themes": ["Cool roofs"],
    **SUMMARY,
}
PROMPTS = []


def fake_models(monkeypatch, draft, supported, redraft=None, follow=None):
    PROMPTS.clear()

    def ask_json(client, size, *, step, **kwargs):
        PROMPTS.append((step, kwargs))
        if step == "follow-up":
            return follow
        if step == "query":  # searches for the question as asked
            return {"query": kwargs["prompt"].removeprefix("Question: ")}
        if step == "draft":
            return {**DRAFT_EXTRAS, **draft}
        if step == "redraft":
            return {**DRAFT_EXTRAS, **(redraft or draft)}
        if step == "verify":
            return {"verdicts": [{"index": i, "supported": i in supported} for i in range(10)]}
        if step == "rewrite":
            return {"query": "urban heat"}
        if step == "plan":  # Quick answer widening its search, or Deep research
            return {"sub_questions": [{"question": "sub", "search_query": "wider search"}]}
        if step == "summary":
            return SUMMARY
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


# --- follow-ups ---

PREVIOUS = {
    "question": "How do cities in Kenya keep cool?",
    "answer": {
        "paragraphs": ["Nairobi planted trees [1]."],
        "report": None,
        "sources": [
            {
                "chunkId": "heat#p6-1",
                "docId": "heat",
                "title": "Heat-resilient cities",
                "pubType": "Technical note",
                "year": 2024,
                "page": 6,
                "printedPage": "4",
                "passage": "Nairobi planted street trees.",
                "quotable": True,
                "pdfKey": "raw/heat.pdf",
            }
        ],
    },
}


class RecordingGateway(FakeGateway):
    def __init__(self, relevance):
        super().__init__(relevance)
        self.queries = []

    def call(self, tool, arguments):
        if tool == "search":
            self.queries.append(arguments["query"])
        return super().call(tool, arguments)


def follow_up(kind, standalone="", audience="auto", language="none", message_language="en"):
    return {
        "kind": kind,
        "language": language,
        "standalone": standalone,
        "audience": audience,
        "message_language": message_language,
    }


def test_a_follow_up_question_is_searched_and_stored_in_context(monkeypatch):
    standalone = "How does Kigali keep cool?"
    fake_models(monkeypatch, DRAFT, {0}, follow=follow_up("new", standalone))
    gateway, memory = RecordingGateway(0.3), FakeMemory(PREVIOUS)
    agent = Agent(Deps(llm=None, gateway=gateway, memory=memory, bedrock=None), SETTINGS)
    events = list(agent.run({"question": "what about Kigali?", "sessionId": "s" * 40}))
    assert gateway.queries[0] == standalone
    assert any(e.get("id") == "context" and e.get("detail") == standalone for e in events)
    assert memory.saved[0][1] == standalone  # the next follow-up reads this one in context
    follow_prompt = next(kwargs["prompt"] for step, kwargs in PROMPTS if step == "follow-up")
    assert "How do cities in Kenya keep cool?" in follow_prompt


def test_a_rewrite_request_reuses_the_previous_sources_without_searching(monkeypatch):
    fake_models(monkeypatch, DRAFT, {0}, follow=follow_up("rewrite", audience="partnerships"))
    gateway, memory = RecordingGateway(0.3), FakeMemory(PREVIOUS)
    agent = Agent(Deps(llm=None, gateway=gateway, memory=memory, bedrock=None), SETTINGS)
    events = list(agent.run({"question": "as talking points for a funder", "sessionId": "s" * 40}))
    answer = events[-1]["answer"]
    assert gateway.queries == []
    assert answer["audience"] == "partnerships"
    assert answer["sources"][0]["chunkId"] == "heat#p6-1"
    assert answer["claimsVerified"] == 1  # verified again, not copied
    draft_prompt = next(kwargs["prompt"] for step, kwargs in PROMPTS if step == "draft")
    assert "Follow-up request: as talking points for a funder" in draft_prompt
    assert "Nairobi planted street trees." in draft_prompt


# --- fact-check ---


def test_fact_check_verdicts_must_rest_on_retrieved_passages_and_their_figures():
    from askwri.agent.factcheck import checked_verdict

    labels = {"P1": {"passage": "In 2024, 181 of 394 cities missed the 2030 standards."}}
    claim = {"claim": "181 of 394 cities missed the standards in 2024."}

    def verdict(kind, passages, correction=""):
        return {"verdict": kind, "passages": passages, "correction": correction, "note": "n"}

    assert checked_verdict(claim, verdict("supported", ["P1"]), ["P1"], labels)["verdict"] == (
        "supported"
    )
    # citing a passage that wasn't retrieved for this claim is not evidence
    assert checked_verdict(claim, verdict("supported", ["P9"]), ["P1"], labels)["verdict"] == (
        "not_found"
    )
    # a "supported" figure the passage doesn't give is not supported
    wrong = {"claim": "281 of 394 cities missed the standards."}
    assert checked_verdict(wrong, verdict("supported", ["P1"]), ["P1"], labels)["verdict"] == (
        "not_found"
    )
    # a correction keeps only figures the passages give
    fixed = checked_verdict(
        wrong, verdict("contradicted", ["P1"], "181 of 394 cities"), ["P1"], labels
    )
    assert (fixed["verdict"], fixed["correction"]) == ("contradicted", "181 of 394 cities")
    invented = verdict("contradicted", ["P1"], "About 200 cities missed them.")
    assert checked_verdict(wrong, invented, ["P1"], labels)["correction"] == ""
    assert checked_verdict(claim, None, ["P1"], labels)["verdict"] == "not_found"


def test_fact_check_mode_returns_claims_with_markers_into_one_sources_list(monkeypatch):
    def ask_json(client, size, *, step, **kwargs):
        if step == "claims":
            return {
                "claims": [
                    {
                        "quote": "Cool roofs cut heat",
                        "claim": "Cool roofs lowered heat.",
                        "query": "q1",
                    },
                    {"quote": "Roofs cure disease", "claim": "Roofs cure disease.", "query": "q2"},
                ]
            }
        if step == "judge":
            return {
                "verdicts": [
                    {
                        "index": 0,
                        "verdict": "supported",
                        "passages": ["P1"],
                        "correction": "",
                        "note": "",
                    },
                    {
                        "index": 1,
                        "verdict": "not_found",
                        "passages": [],
                        "correction": "",
                        "note": "",
                    },
                ]
            }
        if step == "verify":  # the summary's claims
            return {"verdicts": [{"index": 0, "supported": True}]}
        if step == "summary":
            return SUMMARY
        raise AssertionError(step)

    monkeypatch.setattr(llm, "ask_json", ask_json)
    agent = Agent(Deps(llm=None, gateway=FakeGateway(0.3), memory=None, bedrock=None), SETTINGS)
    events = list(
        agent.run({"question": "Cool roofs cut heat. Roofs cure disease.", "mode": "factcheck"})
    )
    check = events[-1]["factcheck"]
    assert [c["verdict"] for c in check["claims"]] == ["supported", "not_found"]
    assert check["claims"][0]["markers"] == [1] and check["claims"][1]["markers"] == []
    assert len(check["sources"]) == 1 and check["counts"]["supported"] == 1


def test_fact_check_notes_show_the_readers_markers_not_internal_labels():
    from askwri.agent.factcheck import readable_note

    assert readable_note("P2 says 181; P7 agrees.", ["P7", "P2"]) == "[2] says 181; [1] agrees."
    assert readable_note("P9 was not cited.", ["P1"]) == "another source was not cited."


# --- languages ---


def run_spanish(monkeypatch, follow=None, previous=None, language="en"):
    """Run with a translating gateway; the drafter says the question was in Spanish."""
    fake_models(monkeypatch, {**DRAFT, "question_language": "es"}, {0}, follow=follow)
    gateway = TranslatingGateway(0.3)
    agent = Agent(
        Deps(llm=None, gateway=gateway, memory=FakeMemory(previous), bedrock=None), SETTINGS
    )
    request = {
        "question": "¿Cómo se enfrían las ciudades?",
        "sessionId": "s" * 40,
        "language": language,
    }
    return list(agent.run(request))[-1]


def test_a_question_asked_in_spanish_is_answered_in_spanish_with_original_sources(monkeypatch):
    answer = run_spanish(monkeypatch)["answer"]
    assert answer["language"] == "es" and answer["machineTranslated"]
    assert answer["paragraphs"] == ["ES: Cool roofs lowered surface heat [1]."]
    assert answer["sources"][0]["title"] == "Heat-resilient cities"  # titles stay original


def test_a_new_question_in_spanish_is_not_mistaken_for_translate(monkeypatch):
    # The classifier says "translate" but names no language it can translate into.
    follow = follow_up("translate", "How do cities cool down?", message_language="es")
    final = run_spanish(monkeypatch, follow=follow, previous=PREVIOUS)
    assert final["type"] == "answer"
    assert final["answer"]["language"] == "es"
    assert final["answer"]["paragraphs"] != PREVIOUS["answer"]["paragraphs"]


def test_deep_fact_check_searches_again_for_claims_not_found(monkeypatch):
    judged = []

    def ask_json(client, size, *, step, **kwargs):
        if step == "claims":
            return {
                "claims": [
                    {"quote": "Roofs cool", "claim": "Cool roofs lowered heat.", "query": "q"}
                ]
            }
        if step == "judge":
            judged.append(kwargs["prompt"])
            settled = len(judged) == 2
            return {
                "verdicts": [
                    {
                        "index": 0,
                        "verdict": "supported" if settled else "not_found",
                        "passages": ["P1"] if settled else [],
                        "correction": "",
                        "note": "",
                    }
                ]
            }
        if step == "verify":  # the summary's claims
            return {"verdicts": [{"index": 0, "supported": True}]}
        if step == "summary":
            return SUMMARY
        raise AssertionError(step)

    monkeypatch.setattr(llm, "ask_json", ask_json)
    gateway = RecordingGateway(0.3)
    agent = Agent(Deps(llm=None, gateway=gateway, memory=None, bedrock=None), SETTINGS)
    request = {"question": "Roofs cool.", "mode": "factcheck", "deep": True}
    check = list(agent.run(request))[-1]["factcheck"]
    assert gateway.queries == ["q", "Cool roofs lowered heat."]  # second round: the claim itself
    assert check["claims"][0]["verdict"] == "supported"


# --- research lens ---


def test_lens_is_cleaned_and_papers_put_the_cited_ones_first():
    from askwri.agent.lens import lens_from, lens_papers

    assert lens_from({"lens": {"goal": " ", "aspects": ["cost"]}}) is None
    lens = lens_from({"lens": {"goal": "Heat plan", "aspects": ["cost", " ", "a", "b", "c", "d"]}})
    assert lens == {"goal": "Heat plan", "aspects": ["cost", "a", "b", "c"]}
    pasted = lens_from({"lens": {"goal": "Heat plan", "aspects": ["finance, costs, who pays"]}})
    assert pasted["aspects"] == ["finance", "costs", "who pays"]
    evidence = {
        "x#1": {"chunk_id": "x#1", "doc_id": "x", "relevance": 0.9},
        "y#1": {"chunk_id": "y#1", "doc_id": "y", "relevance": 0.5},
        "x#2": {"chunk_id": "x#2", "doc_id": "x", "relevance": 0.4},
    }
    assert [p["doc_id"] for p in lens_papers(evidence, ["y"])] == ["y", "x"]


def test_lens_cells_are_cited_summaries_or_not_discussed_and_are_verified(monkeypatch):
    def ask_json(client, size, *, step, **kwargs):
        PROMPTS.append((step, kwargs))
        if step == "query":
            return {"query": "q"}
        if step == "draft":
            return {**DRAFT_EXTRAS, **DRAFT}
        if step == "lens":
            return {
                "aspects": [
                    {
                        "discussed": True,
                        "sentences": [{"text": "Roofs were cheap.", "passages": ["P2"]}],
                    },
                    {"discussed": False, "sentences": []},
                    {
                        "discussed": True,
                        "sentences": [{"text": "Invented claim.", "passages": ["P9"]}],
                    },
                ]
            }
        if step == "verify":  # first claim in each check holds: answer's roofs, lens's cost cell
            return {"verdicts": [{"index": i, "supported": i == 0} for i in range(10)]}
        if step == "summary":
            return SUMMARY
        raise AssertionError(step)

    PROMPTS.clear()
    monkeypatch.setattr(llm, "ask_json", ask_json)

    class LensGateway(RecordingGateway):
        def call(self, tool, arguments):
            if tool == "search" and arguments.get("doc_id"):
                self.queries.append(arguments["query"])
                return {"results": [{**RESULT, "chunk_id": "heat#p9-1", "relevance": 0.2}]}
            return super().call(tool, arguments)

    gateway = LensGateway(0.3)
    agent = Agent(Deps(llm=None, gateway=gateway, memory=None, bedrock=None), SETTINGS)
    lens = {"goal": "Heat plan", "aspects": ["cost", "equity", "speed"]}
    answer = list(agent.run({"question": "q", "lens": lens}))[-1]["answer"]
    cells = answer["lens"]["rows"][0]["cells"]
    # "speed" was summarised, but only by citing a passage not found for it: unverified, which
    # the UI shows as "No verified summary" rather than claiming the paper is silent.
    assert [c["status"] for c in cells] == ["summarised", "not_discussed", "unverified"]
    # The cost cell cites the passage found inside the paper, numbered into the sources list.
    assert cells[0]["text"] == "Roofs were cheap [2]."
    assert answer["sources"][1]["chunkId"] == "heat#p9-1"
    assert "cost (Heat plan)" in gateway.queries
    draft_prompt = next(kwargs["prompt"] for step, kwargs in PROMPTS if step == "draft")
    assert "research goal: Heat plan" in draft_prompt


# --- topic dossier ---


class TwoPaperGateway(TranslatingGateway):
    """Search finds two papers; searching inside a paper returns that paper's passage."""

    def call(self, tool, arguments):
        if tool == "search":
            doc = arguments.get("doc_id")
            heat = {**RESULT, "relevance": 0.3}
            water = {**RESULT, "chunk_id": "water#p3-1", "doc_id": "water", "title": "Water"}
            if doc == "water":
                return {"results": [{**water, "chunk_id": "water#p4-1", "relevance": 0.2}]}
            if doc == "heat":
                return {"results": [{**heat, "chunk_id": "heat#p9-1", "relevance": 0.2}]}
            return {"results": [heat, {**water, "relevance": 0.25}]}
        if tool == "authors":
            return {"documents": [], "people": []}
        return super().call(tool, arguments)


def run_dossier(monkeypatch, compare, language="en"):
    def ask_json(client, size, *, step, **kwargs):
        if step == "plan":
            return {"sub_questions": [{"question": "q", "search_query": "q"}]}
        if step == "draft":
            return {
                **DRAFT_EXTRAS,
                "answerable": True,
                "title": "Cooling",
                "key_points": [{"text": "Roofs cooled cities.", "passages": ["P1"]}],
            }
        if step == "lens":
            found = "P4" if "Water" in kwargs["prompt"] else "P3"
            first = {
                "discussed": True,
                "sentences": [{"text": f"Finding {found}.", "passages": [found]}],
            }
            return {"aspects": [first] + [{"discussed": False, "sentences": []}] * 3}
        if step == "compare":
            return compare
        if step == "verify":
            return {"verdicts": [{"index": i, "supported": True} for i in range(20)]}
        if step == "summary":
            return SUMMARY
        raise AssertionError(step)

    monkeypatch.setattr(llm, "ask_json", ask_json)
    agent = Agent(Deps(llm=None, gateway=TwoPaperGateway(0.3), memory=None, bedrock=None), SETTINGS)
    request = {
        "question": "Cooling cities",
        "mode": "deep",
        "format": "dossier",
        "language": language,
    }
    return list(agent.run(request))[-1]["answer"]


def test_a_dossier_has_a_matrix_and_comparisons_that_span_two_papers(monkeypatch):
    compare = {
        "agree": [
            {"text": "Both papers favour greenery.", "passages": ["P3", "P4"]},
            {"text": "Only one paper is cited here.", "passages": ["P3"]},  # not a comparison
        ],
        "differ": [{"text": "They differ on cost.", "passages": ["P4", "P3", "P99"]}],
        "missing": ["Neither covers costs in 2050."],
    }
    answer = run_dossier(monkeypatch, compare)
    assert answer["lens"]["aspects"] == loop.DOSSIER_ASPECTS
    assert [row["docId"] for row in answer["lens"]["rows"]] == ["heat", "water"]
    dossier = answer["dossier"]
    assert dossier["agree"] == ["Both papers favour greenery [2][3]."]
    assert dossier["differ"] == ["They differ on cost [3][2]."]
    assert dossier["missing"] == []  # "2050" is a number no passage gave


def test_a_translated_answer_translates_lens_cells_and_dossier_too(monkeypatch):
    compare = {
        "agree": [{"text": "Both agree.", "passages": ["P3", "P4"]}],
        "differ": [],
        "missing": ["No costs."],
    }
    answer = run_dossier(monkeypatch, compare, language="es")
    cells = [c for row in answer["lens"]["rows"] for c in row["cells"]]
    assert cells[0]["text"].startswith("ES: Finding")
    assert cells[1] == {"status": "not_discussed", "text": ""}
    assert answer["dossier"]["agree"][0].startswith("ES: Both agree")
    assert answer["dossier"]["missing"] == ["ES: No costs."]


def test_reader_facing_text_never_says_passages():
    from askwri.agent.citations import readers_words

    assert readers_words("The passages do not rank other laws.") == (
        "The cited WRI publications do not rank other laws."
    )
    assert readers_words("None of these passages covers 2050.") == (
        "None of the cited WRI publications covers 2050."
    )
    assert readers_words("A passage says so.") == "A cited WRI publication says so."
    assert "passage" not in readers_words("Two passages agree; one passage differs.").lower()


# --- visuals ---

LINK = {
    "src_doc_id": "new",
    "src_title": "From Tracking to Action",
    "src_year": 2015,
    "src_pdf_key": "raw/new.pdf",
    "dst_doc_id": "old",
    "dst_title": "Tracking Adaptation Finance",
    "dst_year": 2012,
    "dst_pdf_key": "raw/old.pdf",
    "relation": "extends",
    "aspect": "tracking method",
    "confidence": 0.8,
    "match_method": "title",
    "context_sentence": "We build on Tracking Adaptation Finance.",
    "context_page": 9,
}


def visual_source(marker, doc, year, passage="Funds reached 120 projects in 2014."):
    return {
        "marker": marker,
        "docId": doc,
        "title": doc.title(),
        "year": year,
        "pubType": "Report",
        "dateConfidence": "high" if year else "undated",
        "passage": passage,
        "quotable": True,
    }


def test_timeline_and_citation_flow_are_built_from_the_answer_and_its_links():
    from askwri.agent.visuals import citation_flow, documents, timeline

    sources = [visual_source(1, "new", 2015), visual_source(2, "other", None)]
    docs = documents(sources)
    line = timeline(docs, [LINK], {"old": 1})
    assert [p["docId"] for p in line["points"]] == ["old", "new"]  # the cited report joins the axis
    assert line["points"][0]["citedInAnswer"] is False and line["points"][0]["citedBy"] == 1
    assert [p["docId"] for p in line["undated"]] == ["other"]
    assert line["caption"] == "2 dated WRI publications, 2012 to 2015, and 1 undated"

    flow = citation_flow(docs, [LINK], ["Tracking moved to action [1]. Other work agrees [2]."])
    new = flow["flows"]["new"]
    assert flow["defaultFocus"] == "new"
    assert new["cites"][0]["docId"] == "old" and new["cites"][0]["relation"] == "extends"
    assert (new["cites"][0]["page"], new["cites"][0]["pdfKey"]) == (9, "raw/new.pdf")  # citing page
    assert new["mainPoint"] == "Tracking moved to action [1]."
    assert flow["caption"] == "1 of 2 reports link to other reports in AskWRI's collection"


def test_key_figures_keep_only_values_found_word_for_word_one_per_document():
    from askwri.agent.visuals import checked_figures

    sources = [
        visual_source(1, "a", 2015, "In 2024, 181 of 394 cities missed it."),
        visual_source(2, "b", 2016, "Returns reached 23 percent."),
    ]
    figures = [
        {
            "value": "181",
            "unit": "cities",
            "what": "missed the standard",
            "place": "",
            "year": "2024",
            "marker": 1,
        },
        {
            "value": "394",
            "unit": "cities",
            "what": "studied",
            "place": "",
            "year": "",
            "marker": 1,
        },  # same doc
        {
            "value": "18",
            "unit": "",
            "what": "inside 181, not a figure",
            "place": "",
            "year": "",
            "marker": 2,
        },
        {
            "value": "25",
            "unit": "%",
            "what": "rounded, not in the passage",
            "place": "",
            "year": "",
            "marker": 2,
        },
        {"value": "23", "unit": "%", "what": "returns", "place": "", "year": "", "marker": 2},
    ]
    assert [(c["value"], c["docId"]) for c in checked_figures(figures, sources)] == [
        ("181", "a"),
        ("23", "b"),
    ]


def test_a_reader_the_user_picked_beats_the_one_the_follow_up_suggests(monkeypatch):
    fake_models(monkeypatch, DRAFT, {0}, follow=follow_up("rewrite", audience="policymaker"))
    agent = Agent(
        Deps(llm=None, gateway=RecordingGateway(0.3), memory=FakeMemory(PREVIOUS), bedrock=None),
        SETTINGS,
    )
    request = {"question": "same question again", "sessionId": "s" * 40, "audience": "partnerships"}
    assert list(agent.run(request))[-1]["answer"]["audience"] == "partnerships"


def test_every_final_event_reports_what_the_question_used(monkeypatch):
    sent = []
    monkeypatch.setattr(loop.usage, "publish", sent.append)
    fake_models(monkeypatch, DRAFT, {0})
    loop.usage.record("draft", "global.anthropic.claude-sonnet-5-5", 1000, 200)  # cleared on start
    agent = Agent(Deps(llm=None, gateway=FakeGateway(0.3), memory=None, bedrock=None), SETTINGS)
    answer = list(agent.run({"question": "q", "source": "eval"}))[-1]
    assert answer["usage"]["modelCalls"] == 0  # the fakes make no real calls
    points = {p["MetricName"]: p for p in sent[0]}
    assert points["Questions"]["Value"] == 1 and points["Declined"]["Value"] == 0
    assert {"Name": "Source", "Value": "eval"} in points["Questions"]["Dimensions"]
    assert points["ClaimsRemoved"]["Value"] == 1


def test_usage_estimates_cost_per_model_and_step():
    from askwri.agent import usage

    usage.reset()
    usage.record("draft", "global.anthropic.claude-sonnet-5-5", 1_000_000, 100_000)
    usage.record("verify", "global.anthropic.claude-haiku-4-5-20251001-v1:0", 1_000_000, 0)
    used = usage.summary()
    assert used["byStep"] == {
        "draft": {"in": 1_000_000, "out": 100_000},
        "verify": {"in": 1_000_000, "out": 0},
    }
    assert used["estimatedCostUsd"] == 3.0 + 1.5 + 1.0


def test_topic_and_region_filters_reach_the_search_tool():
    arguments = loop.search_arguments("heat", "quick", {"topic": "Ocean", "region": "Africa"})
    assert (arguments["topic"], arguments["country"]) == ("Ocean", "Africa")


# --- quick answer's search query, parallel deep searches, report formats, languages ---


def test_quick_answer_searches_a_short_query_not_the_whole_question(monkeypatch):
    fake_models(monkeypatch, DRAFT, {0})

    def ask_json(client, size, *, step, **kwargs):
        if step == "query":
            return {"query": "EU environmental laws"}
        return fake(client, size, step=step, **kwargs)

    fake = llm.ask_json
    monkeypatch.setattr(llm, "ask_json", ask_json)
    gateway = RecordingGateway(0.3)
    agent = Agent(Deps(llm=None, gateway=gateway, memory=None, bedrock=None), SETTINGS)
    question = "I want to build a policy initiative in Europe. What key laws should we target?"
    events = list(agent.run({"question": question}))
    assert gateway.queries == ["EU environmental laws"]
    assert events[-1]["type"] == "answer"
    query_step = next(e for e in events if e.get("id") == "query" and e["status"] == "done")
    assert query_step["detail"] == "EU environmental laws"


def test_deep_research_searches_every_sub_question_and_merges_their_evidence(monkeypatch):
    subs = [{"question": f"sub {i}", "search_query": f"query {i}"} for i in range(3)]
    monkeypatch.setattr(loop.Agent, "_plan", lambda self, q, m: iter_return(subs))
    draft = {
        "answerable": True,
        "title": "Cooling",
        "key_points": [{"text": "Cool roofs lowered surface heat.", "passages": ["P1"]}],
    }
    fake_models(monkeypatch, draft, {0})
    gateway = RecordingGateway(0.3)
    agent = Agent(Deps(llm=None, gateway=gateway, memory=None, bedrock=None), SETTINGS)
    events = list(agent.run({"question": "q", "mode": "deep"}))
    assert sorted(gateway.queries) == ["query 0", "query 1", "query 2"]
    # The three searches found the same document: it is announced once.
    assert sum(e["type"] == "source-found" for e in events) == 1
    final = events[-1]
    assert final["type"] == "answer"
    assert final["answer"]["sources"][0]["chunkId"] == "heat#p4-1"


def test_a_failing_sub_question_search_fails_the_run(monkeypatch):
    subs = [{"question": f"sub {i}", "search_query": f"query {i}"} for i in range(2)]
    monkeypatch.setattr(loop.Agent, "_plan", lambda self, q, m: iter_return(subs))
    fake_models(monkeypatch, DRAFT, {0})

    class BrokenGateway(FakeGateway):
        def call(self, tool, arguments):
            if tool == "search" and arguments["query"] == "query 1":
                raise RuntimeError("search is down")
            return super().call(tool, arguments)

    agent = Agent(Deps(llm=None, gateway=BrokenGateway(0.3), memory=None, bedrock=None), SETTINGS)
    with pytest.raises(RuntimeError, match="search is down"):
        list(agent.run({"question": "q", "mode": "deep"}))


def draft_prompt_for(monkeypatch, report_format):
    monkeypatch.setattr(
        loop.Agent, "_plan", lambda self, q, m: iter_return([{"question": q, "search_query": q}])
    )
    draft = {
        "answerable": True,
        "title": "Cooling",
        "key_points": [{"text": "Cool roofs lowered surface heat.", "passages": ["P1"]}],
    }
    fake_models(monkeypatch, draft, {0})
    agent = Agent(Deps(llm=None, gateway=FakeGateway(0.3), memory=None, bedrock=None), SETTINGS)
    list(agent.run({"question": "q", "mode": "deep", "format": report_format}))
    return next(kwargs["prompt"] for step, kwargs in PROMPTS if step == "draft")


def test_issue_briefs_and_talking_points_ask_for_different_structures(monkeypatch):
    brief = draft_prompt_for(monkeypatch, "issue-brief")
    points = draft_prompt_for(monkeypatch, "talking-points")
    assert "the problem and why it matters" in brief and "options" in brief
    assert "say aloud in a meeting" in points and "under 25 words" in points
    assert "say aloud" not in brief and "the problem and why it matters" not in points


def test_memory_keeps_the_english_answer_when_the_user_sees_a_translation(monkeypatch):
    fake_models(monkeypatch, DRAFT, {0})
    memory = FakeMemory()
    agent = Agent(
        Deps(llm=None, gateway=TranslatingGateway(0.3), memory=memory, bedrock=None), SETTINGS
    )
    request = {"question": "How do cities cool down?", "sessionId": "s" * 40, "language": "es"}
    shown = list(agent.run(request))[-1]["answer"]
    stored = memory.saved[0][2]
    assert shown["language"] == "es" and shown["paragraphs"][0].startswith("ES: ")
    assert stored["language"] == "en" and not stored["machineTranslated"]
    assert stored["paragraphs"] == ["Cool roofs lowered surface heat [1]."]


def test_now_in_english_after_a_spanish_answer_shows_the_english_answer(monkeypatch):
    english = {**PREVIOUS["answer"], "language": "en", "machineTranslated": False}
    follow = follow_up("translate", language="en")
    fake_models(monkeypatch, DRAFT, {0}, follow=follow)
    memory = FakeMemory({"question": PREVIOUS["question"], "answer": english})
    agent = Agent(
        Deps(llm=None, gateway=TranslatingGateway(0.3), memory=memory, bedrock=None), SETTINGS
    )
    request = {"question": "Now in English", "sessionId": "s" * 40, "language": "en"}
    answer = list(agent.run(request))[-1]["answer"]
    assert answer["language"] == "en" and not answer["machineTranslated"]
    assert answer["paragraphs"] == ["Nairobi planted trees [1]."]
    assert memory.saved[0][2] == english  # still English for the next turn


def test_translate_translates_the_answer_sent_not_the_sessions_latest(monkeypatch):
    fake_models(monkeypatch, DRAFT, {0})
    memory = FakeMemory(PREVIOUS)  # the session's latest turn is a different answer
    gateway = TranslatingGateway(0.3)
    agent = Agent(Deps(llm=None, gateway=gateway, memory=memory, bedrock=None), SETTINGS)
    clicked = {"paragraphs": ["Older answer [1]."], "report": None, "sources": [], "language": "en"}
    request = {
        "question": "Now in Spanish",
        "mode": "translate",
        "language": "es",
        "sessionId": "s" * 40,
        "answer": clicked,
    }
    answer = list(agent.run(request))[-1]["answer"]
    assert answer["paragraphs"] == ["ES: Older answer [1]."]
    assert answer["language"] == "es" and answer["machineTranslated"]
    assert not memory.saved  # translating adds no turn


def test_a_spanish_answer_can_be_translated_into_english():
    agent = Agent(
        Deps(llm=None, gateway=TranslatingGateway(0.3), memory=None, bedrock=None), SETTINGS
    )
    spanish = {"paragraphs": ["Hola [1]."], "report": None, "sources": [], "language": "es"}
    events = list(
        agent.run({"question": "q", "mode": "translate", "language": "en", "answer": spanish})
    )
    assert events[-1]["answer"]["paragraphs"] == ["ES: Hola [1]."]  # the fake marks what it sent
    assert events[-1]["answer"]["language"] == "en"


def test_a_new_format_redrafts_from_the_answers_own_sources_without_searching(monkeypatch):
    draft = {
        "answerable": True,
        "title": "Cooling",
        "key_points": [{"text": "Nairobi planted street trees.", "passages": ["P1"]}],
    }
    fake_models(monkeypatch, draft, {0})
    gateway, memory = RecordingGateway(0.3), FakeMemory()
    agent = Agent(Deps(llm=None, gateway=gateway, memory=memory, bedrock=None), SETTINGS)
    request = {
        "question": "How do cities in Kenya keep cool?",
        "mode": "deep",
        "format": "talking-points",
        "reuse": True,
        "answer": PREVIOUS["answer"],
        "sessionId": "s" * 40,
    }
    answer = list(agent.run(request))[-1]["answer"]
    assert gateway.queries == []
    assert answer["sources"][0]["chunkId"] == "heat#p6-1"
    draft_prompt = next(kwargs["prompt"] for step, kwargs in PROMPTS if step == "draft")
    assert "talking points for a partner meeting" in draft_prompt
    assert "Nairobi planted street trees." in draft_prompt


def test_answers_never_say_passages_to_the_reader(monkeypatch):
    draft = {
        "answerable": True,
        "paragraphs": [
            {"sentences": [{"text": "The passages point to cool roofs.", "passages": ["P1"]}]}
        ],
    }
    events, _ = run(monkeypatch, relevance=0.3, draft=draft, supported=(0,))
    assert events[-1]["answer"]["paragraphs"] == [
        "The cited WRI publications point to cool roofs [1]."
    ]


# --- Quick answer widens its search before it declines ---


class WiderGateway(RecordingGateway):
    """Weak evidence for the quick search, strong for the wider one."""

    def call(self, tool, arguments):
        if tool == "search":
            self.queries.append(arguments["query"])
            strong = arguments["query"] == "wider search"
            return {"results": [{**RESULT, "relevance": 0.5 if strong else 0.01}]}
        return FakeGateway.call(self, tool, arguments)


ONE_CLAIM = {
    "answerable": True,
    "paragraphs": [
        {"sentences": [{"text": "Cool roofs lowered surface heat.", "passages": ["P1"]}]}
    ],
}


def test_weak_quick_evidence_widens_the_search_and_answers(monkeypatch):
    fake_models(monkeypatch, ONE_CLAIM, {0})
    gateway = WiderGateway(0.01)
    agent = Agent(Deps(llm=None, gateway=gateway, memory=None, bedrock=None), SETTINGS)
    events = list(agent.run({"question": "How do cities cool down?"}))
    assert gateway.queries == ["How do cities cool down?", "urban heat", "wider search"]
    assert any(e.get("id") == "widen" for e in events)
    answer = events[-1]["answer"]
    assert answer["widened"] and answer["mode"] == "quick"
    assert answer["paragraphs"] == ["Cool roofs lowered surface heat [1]."]  # still verified
    ids = [e["id"] for e in events if e["type"] == "step" and e["status"] == "done"]
    assert len(ids) == len(set(ids))  # the wider search's steps don't overwrite the first's


def test_quick_draft_that_cannot_answer_widens_once_then_answers(monkeypatch):
    drafts = iter([{"answerable": False, "paragraphs": []}, ONE_CLAIM])
    fake_models(monkeypatch, ONE_CLAIM, {0})
    fake = llm.ask_json

    def ask_json(client, size, *, step, **kwargs):
        if step == "draft":
            return {**DRAFT_EXTRAS, **next(drafts)}
        return fake(client, size, step=step, **kwargs)

    monkeypatch.setattr(llm, "ask_json", ask_json)
    gateway = RecordingGateway(0.3)
    agent = Agent(Deps(llm=None, gateway=gateway, memory=None, bedrock=None), SETTINGS)
    events = list(agent.run({"question": "How do cities cool down?"}))
    assert events[-1]["type"] == "answer" and events[-1]["answer"]["widened"]
    assert "wider search" in gateway.queries


def test_widening_never_shows_claims_that_fail_verification(monkeypatch):
    events, _ = run(monkeypatch, relevance=0.3, supported=())
    assert any(e.get("id") == "widen" for e in events)
    assert events[-1]["type"] == "decline"  # nothing verified on either attempt


def test_deep_research_never_widens(monkeypatch):
    monkeypatch.setattr(
        loop.Agent, "_plan", lambda self, q, m: iter_return([{"question": q, "search_query": q}])
    )
    fake_models(monkeypatch, DRAFT, {0})
    agent = Agent(Deps(llm=None, gateway=FakeGateway(0.01), memory=None, bedrock=None), SETTINGS)
    events = list(agent.run({"question": "q", "mode": "deep"}))
    assert events[-1]["type"] == "decline"
    assert not any(e.get("id") == "widen" for e in events)


def test_a_widened_answer_needs_most_of_its_claims_verified(monkeypatch):
    # Two claims, one verified: shown for an ordinary quick answer, declined once widened.
    fake_models(monkeypatch, DRAFT, {0})
    agent = Agent(Deps(llm=None, gateway=WiderGateway(0.01), memory=None, bedrock=None), SETTINGS)
    events = list(agent.run({"question": "How do cities cool down?"}))
    assert events[-1]["type"] == "decline"
    events, _ = run(monkeypatch, relevance=0.3)
    assert events[-1]["type"] == "answer"


def test_the_drafter_is_told_to_decline_false_premises(monkeypatch):
    run(monkeypatch, relevance=0.3)
    system = next(kwargs["system"] for step, kwargs in PROMPTS if step == "draft")
    assert "takes for granted something the passages do not state" in system


# --- the summary shown first in every mode ---


def test_an_answer_opens_with_a_verified_summary_citing_its_sources(monkeypatch):
    # Claims 0 and 1 are the answer's, claim 2 the summary's: all three share one check.
    events, memory = run(monkeypatch, relevance=0.3, supported=(0, 2))
    answer = events[-1]["answer"]
    assert answer["summary"] == ["In short, roofs cool cities [1]."]
    assert answer["sources"][0]["marker"] == 1  # the summary's marker is in the sources list
    assert answer["themes"] == ["Cool roofs"]  # one matrix column heading per paragraph
    assert memory.saved[0][2]["summary"] == answer["summary"]
    # Written by the draft call itself: no second model call for it.
    prompt = next(kwargs["prompt"] for step, kwargs in PROMPTS if step == "draft")
    assert "synthesises what these WRI publications" in prompt
    assert not any(step == "summary" for step, _ in PROMPTS)


def test_summary_sentences_that_fail_verification_or_cite_nothing_real_are_dropped(monkeypatch):
    summary = [
        {"text": "Invented source.", "passages": ["P9"]},
        {"text": "Fails its check.", "passages": ["P1"]},
    ]
    # Claims 0 and 1 are the answer's; claim 2 is the summary's, and it fails.
    fake_models(monkeypatch, {**DRAFT, "summary": summary}, {0})
    agent = Agent(Deps(llm=None, gateway=FakeGateway(0.3), memory=None, bedrock=None), SETTINGS)
    answer = list(agent.run({"question": "How do cities cool down?"}))[-1]["answer"]
    assert answer["summary"] == []
    check = next(kwargs["prompt"] for step, kwargs in PROMPTS if step == "verify")
    assert "Invented source" not in check and "Fails its check" in check
    assert answer["paragraphs"]  # the answer itself still shows
    assert answer["claimsTotal"] == 2  # summary sentences are not counted as the answer's claims


def test_explore_opens_with_a_summary_too(monkeypatch):
    fake_models(monkeypatch, DRAFT, {0})
    monkeypatch.setattr(
        loop, "build_visuals", lambda gateway, client, topic, sources, links: {"timeline": {}}
    )
    agent = Agent(Deps(llm=None, gateway=FakeGateway(0.3), memory=None, bedrock=None), SETTINGS)
    explored = list(agent.run({"question": "cool roofs", "mode": "explore"}))[-1]
    assert explored["type"] == "visuals"
    assert explored["summary"] == ["In short, roofs cool cities [1]."]


def test_a_translated_answer_translates_its_summary(monkeypatch):
    fake_models(monkeypatch, DRAFT, {0, 2})
    agent = Agent(
        Deps(llm=None, gateway=TranslatingGateway(0.3), memory=None, bedrock=None), SETTINGS
    )
    answer = list(agent.run({"question": "q", "language": "es"}))[-1]["answer"]
    assert answer["summary"] == ["ES: In short, roofs cool cities [1]."]


def test_each_summary_sentence_is_grounded_against_its_own_passages(monkeypatch):
    summary = [
        {"text": "Roofs cool cities.", "passages": ["P1"]},
        {"text": "They also cured all diseases.", "passages": ["P1"]},
    ]
    fake_models(monkeypatch, {**ONE_CLAIM, "summary": summary}, set(range(10)))
    settings = Settings(0.1, 2, 3, guardrail_id="g", guardrail_version="1")
    agent = Agent(
        Deps(llm=None, gateway=FakeGateway(0.3), memory=None, bedrock=FakeGuardrail()), settings
    )
    answer = list(agent.run({"question": "How do cities cool down?"}))[-1]["answer"]
    # The guardrail fails only the sentence about diseases; the other one stays.
    assert answer["summary"] == ["Roofs cool cities [1]."]


def test_passage_labels_written_into_a_summary_never_reach_the_reader(monkeypatch):
    text = "Roofs cool cities [P1] and parks help (P1, P1)."
    fake_models(monkeypatch, {**ONE_CLAIM, "summary": [{"text": text, "passages": ["P1"]}]}, {0, 1})
    agent = Agent(Deps(llm=None, gateway=FakeGateway(0.3), memory=None, bedrock=None), SETTINGS)
    answer = list(agent.run({"question": "How do cities cool down?"}))[-1]["answer"]
    assert answer["summary"] == ["Roofs cool cities and parks help [1]."]


def test_each_kept_paragraph_keeps_its_theme_for_the_matrix_columns():
    a = [loop.Sentence("Roofs cool.", ("P1",)), loop.Sentence("Paint helps.", ("P2",))]
    b = [loop.Sentence("Buses are faster.", ("P3",))]
    c = [loop.Sentence("Trees shade.", ("P4",))]
    # The second paragraph failed verification; the first lost one sentence.
    kept = [[a[1]], c]
    assert loop.group_themes([a, b, c], ["Roofs", "Buses", "Trees"], kept) == ["Roofs", "Trees"]
    assert loop.group_themes([a], [], [[a[0]]]) == [""]


def test_a_dossier_too_large_for_one_memory_message_is_stored_smaller():
    import json

    from askwri.agent.memory import ANSWER_KEY, MAX_STORED, stored_text

    source = {"marker": 1, "passage": "x" * 5000}
    small = {"paragraphs": ["a [1]."], "sources": [source]}
    assert json.loads(stored_text(small))[ANSWER_KEY] == small
    big = {
        **small,
        "sources": [source] * 30,
        "lens": {"rows": ["y" * 80_000]},
        "dossier": {"agree": []},
    }
    kept = json.loads(stored_text(big))[ANSWER_KEY]
    assert len(stored_text(big)) <= MAX_STORED
    assert "lens" not in kept and kept["paragraphs"] == ["a [1]."]
    assert len(kept["sources"][0]["passage"]) == 1200
    huge = {**small, "sources": [{"marker": i, "passage": "z" * 1200} for i in range(200)]}
    assert (
        json.loads(stored_text(huge))[ANSWER_KEY]["sources"][0]["marker"] == 0
    )  # still valid JSON
    assert len(stored_text(huge)) <= MAX_STORED


def test_a_model_reply_instead_of_a_translation_is_not_used():
    assert loop.is_translation("Planning and data", "Planificación y datos")
    reply = 'I need more text to translate. You\'ve only provided "Planning and data" in your instructions.'
    assert not loop.is_translation("Planning and data", reply)
    assert not loop.is_translation("Cool roofs", "  ")
