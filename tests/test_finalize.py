"""The answer event: marker renumbering, sources, people, builtFrom and the decline handoff."""

import time

from askwri.answer.finalize import built_from, respond
from tests.answer_fakes import FakeGrounding, passage

REQUEST = {"question": "What about solar?", "mode": "quick"}


def sentence(text, *cites):
    return {"text": text, "cites": list(cites)}


def draft(paragraphs, passages, report=None, **fields):
    return {
        "answerable": True,
        "passages": passages,
        "paragraphs": paragraphs,
        "report": report,
        "searched": ["solar"],
        "seen": passages,
        "suggestions": [],
    } | fields


def answer_for(d, grounding=None):
    event = respond(d, REQUEST, grounding=grounding, started_at=time.monotonic())
    assert event["type"] == "answer", event
    return event["answer"]


def test_markers_are_renumbered_by_first_use_and_sources_match_them():
    passages = [passage(n) for n in range(1, 5)]
    paragraphs = [
        [sentence("Solar grew fast.", 3, 1), sentence("Storage followed", 1)],
        [sentence("Grids lag?", 4, 3, 4)],
    ]
    answer = answer_for(draft(paragraphs, passages))
    assert answer["paragraphs"] == [
        "Solar grew fast [1][2]. Storage followed [2]",
        "Grids lag [3][1]?",
    ]
    assert [(s["marker"], s["chunkId"]) for s in answer["sources"]] == [
        (1, passages[2].chunk_id),
        (2, passages[0].chunk_id),
        (3, passages[3].chunk_id),
    ]


def test_dropped_sentences_leave_no_marker_and_no_source():
    passages = [passage(1), passage(2, text="Wind grew 7%.")]
    paragraphs = [[sentence("Wind grew 9%.", 2), sentence("Solar grew.", 1)]]
    answer = answer_for(draft(paragraphs, passages))
    assert answer["paragraphs"] == ["Solar grew [1]."]
    assert [s["chunkId"] for s in answer["sources"]] == [passages[0].chunk_id]
    assert (answer["claimsTotal"], answer["claimsVerified"]) == (2, 1)


def test_source_carries_every_citation_field():
    p = passage(1, authors=("Ana Lima",), quotable=False, kind="chart", figure_image="fig/1.png")
    source = answer_for(draft([[sentence("Solar grew.", 1)]], [p]))["sources"][0]
    assert source == {
        "marker": 1,
        "chunkId": p.chunk_id,
        "docId": p.doc_id,
        "title": p.doc_title,
        "docType": p.doc_type,
        "wriType": p.wri_type,
        "topic": p.topic,
        "year": p.year,
        "pdfPage": p.pdf_page,
        "pdfPageEnd": p.pdf_page_end,
        "printedPage": p.printed_page,
        "printedPageEnd": p.printed_page_end,
        "printedPageFallback": p.printed_page_fallback,
        "section": p.section,
        "kind": "chart",
        "passage": p.text,
        "quotable": False,
        "url": p.link,
        "pdfKey": p.pdf_key,
        "figureImage": "fig/1.png",
        "authors": ["Ana Lima"],
    }


def test_answer_fields_for_quick_answer():
    answer = answer_for(draft([[sentence("Solar grew.", 1)]], [passage(1)]), FakeGrounding())
    assert answer["mode"] == "quick"
    assert answer["language"] == "en"
    assert answer["machineTranslated"] is False
    assert answer["original"] is None
    assert answer["coverage"] is None
    assert answer["report"] is None
    assert answer["groundingCheck"] == "guardrails"
    assert answer["elapsedSeconds"] >= 0


def test_people_are_most_cited_first_with_their_documents():
    passages = [
        passage(1, doc_id="a", authors=("Ana", "Ben")),
        passage(2, doc_id="b", authors=("Ben",)),
        passage(3, doc_id="b", authors=("Ben", "Cy")),
    ]
    paragraphs = [[sentence("One.", 1), sentence("Two.", 2), sentence("Three.", 3)]]
    people = answer_for(draft(paragraphs, passages))["people"]
    assert people == [
        {"name": "Ben", "docIds": ["a", "b"]},
        {"name": "Ana", "docIds": ["a"]},
        {"name": "Cy", "docIds": ["b"]},
    ]


def test_people_is_empty_without_authors_and_capped_at_five():
    assert answer_for(draft([[sentence("One.", 1)]], [passage(1)]))["people"] == []
    many = passage(1, authors=tuple("ABCDEFG"))
    assert len(answer_for(draft([[sentence("One.", 1)]], [many]))["people"]) == 5


def test_report_key_points_share_marker_numbering_and_get_built_from():
    passages = [passage(1, year=2024), passage(2, year=2026), passage(3, year=2025)]
    report = {
        "title": "Solar brief",
        "audience": "policymaker",
        "format": "issue-brief",
        "key_points": [sentence("Storage leads.", 2), sentence("Solar grew.", 1)],
        "thin_evidence": ["Little on rooftop solar."],
        "gaps": ["No 2023 publications."],
    }
    d = draft([[sentence("Solar grew.", 1)]], passages, report, suggestions=["What about wind?"])
    answer = answer_for(d)
    assert answer["paragraphs"] == ["Solar grew [1]."]
    assert answer["report"] == {
        "title": "Solar brief",
        "audience": "policymaker",
        "format": "issue-brief",
        "builtFrom": "Built from 2 WRI publications, 2024 to 2026",
        "keyPoints": ["Storage leads [2].", "Solar grew [1]."],
        "thinEvidence": ["Little on rooftop solar."],
        "gaps": ["No 2023 publications."],
    }
    assert answer["suggestions"] == ["What about wind?"]
    assert len(answer["sources"]) == 2


def test_built_from_counts_documents_and_handles_one_year_or_none():
    assert built_from([passage(1, doc_id="a"), passage(2, doc_id="a")]) == (
        "Built from 1 WRI publication, 2025"
    )
    assert built_from([passage(1, year=None), passage(2, year=None)]) == (
        "Built from 2 WRI publications"
    )


def test_respond_declines_when_too_few_claims_survive():
    paragraphs = [[sentence("Unsourced."), sentence("Also unsourced."), sentence("Fine.", 1)]]
    event = respond(
        draft(paragraphs, [passage(1)]), REQUEST, grounding=None, started_at=time.monotonic()
    )
    assert event["type"] == "decline"
    assert event["decline"]["reason"] == "unverified"
