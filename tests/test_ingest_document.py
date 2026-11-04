"""Single-document ingestion, driven through synthetic PDFs built in the tests."""

import dataclasses
from pathlib import Path

import pymupdf
import pytest

from askwri.ingest.audit import audit_chunks
from askwri.ingest.document import ingest_document

PARAGRAPH = (
    "Forests store large amounts of carbon and support the livelihoods of many communities. "
    "Protecting them requires secure land rights, transparent monitoring and finance that "
    "reaches local groups. "
)


def two_column_report(path: Path) -> Path:
    """A titled report: two sections, a two-column page, then a page with no text layer."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 70), "Restoring Degraded Land", fontsize=22, fontname="hebo")
    page.insert_text((50, 110), "Introduction", fontsize=15, fontname="hebo")
    page.insert_textbox(pymupdf.Rect(50, 120, 290, 400), PARAGRAPH * 3, fontsize=10)
    page.insert_textbox(
        pymupdf.Rect(310, 120, 550, 400),
        (PARAGRAPH * 3).replace("Forests", "Grasslands"),
        fontsize=10,
    )
    page.insert_text((50, 430), "Methods", fontsize=15, fontname="hebo")
    page.insert_textbox(
        pymupdf.Rect(50, 440, 550, 600), (PARAGRAPH * 3).replace("Forests", "Wetlands"), fontsize=10
    )
    scanned = doc.new_page()
    scanned.draw_rect(pymupdf.Rect(100, 100, 400, 400), color=(0, 0, 0), fill=(0.5, 0.5, 0.5))
    doc.set_metadata({"title": "Restoring Degraded Land"})
    doc.save(path)
    return path


def long_section_report(path: Path) -> Path:
    """One section whose paragraphs fill a page and run onto the next."""
    doc = pymupdf.open()
    first = doc.new_page()
    first.insert_text((50, 70), "Findings", fontsize=15, fontname="hebo")
    for n, top in enumerate((90, 270, 450, 630)):
        text = (PARAGRAPH * 3).replace("Forests", f"Region {n} forests")
        first.insert_textbox(pymupdf.Rect(50, top, 550, top + 170), text, fontsize=10)
    second = doc.new_page()
    second.insert_textbox(
        pymupdf.Rect(50, 70, 550, 240), (PARAGRAPH * 3).replace("Forests", "Mangroves"), fontsize=10
    )
    doc.set_metadata({"title": "Forest Findings"})
    doc.save(path)
    return path


@pytest.fixture(scope="module")
def report(tmp_path_factory) -> Path:
    return two_column_report(tmp_path_factory.mktemp("pdf") / "Restoring Degraded Land v2.pdf")


@pytest.fixture(scope="module")
def result(report):
    return ingest_document(report)


def test_chunks_follow_sections_and_carry_their_address(result):
    by_section = {chunk.section: chunk for chunk in result.chunks}

    assert [chunk.section for chunk in result.chunks] == ["Introduction", "Methods"]
    intro, methods = by_section["Introduction"], by_section["Methods"]
    assert intro.indexed_text.startswith("Restoring Degraded Land › Introduction\n\n")
    assert intro.text.index("Forests") < intro.text.index("Grasslands")
    assert "Wetlands" not in intro.text
    assert methods.text.startswith("Wetlands store large amounts of carbon")
    assert intro.chunk_id == "restoring-degraded-land-v2#p1-1"
    assert (intro.doc_id, intro.doc_title, intro.pdf_page, intro.kind) == (
        "restoring-degraded-land-v2",
        "Restoring Degraded Land",
        1,
        "source_text",
    )


def test_chunk_ids_are_identical_across_runs(report, result):
    rerun = ingest_document(report)

    assert [c.chunk_id for c in rerun.chunks] == [c.chunk_id for c in result.chunks]


def test_audit_passes_and_reports_the_page_without_text_layer(result):
    assert result.audit.passed, result.audit.failures
    assert result.audit.pages_without_text == [2]
    assert result.audit.unquotable == []
    assert all(chunk.quotable for chunk in result.chunks)


def test_audit_keeps_a_reordered_passage_but_marks_it_not_quotable(report, result):
    words = result.chunks[0].text.split()
    shuffled = " ".join(words[len(words) // 2 :] + words[: len(words) // 2])
    reordered = dataclasses.replace(result.chunks[0], text=shuffled)

    audit = audit_chunks(report, [reordered])

    assert audit.passed, audit.failures
    assert audit.unquotable == [reordered.chunk_id]


def test_audit_fails_for_a_passage_claimed_on_the_wrong_page(report, result):
    moved = dataclasses.replace(result.chunks[0], pdf_page=2, pdf_page_end=2)

    audit = audit_chunks(report, [moved])

    assert not audit.passed
    assert audit.failures[0].startswith(f"{moved.chunk_id}: passage not found on page 2")


@pytest.mark.parametrize(
    ("text", "reason"), [("", "empty chunk"), ("### --- ••• ¶¶¶ 1 —", "mostly non-text")]
)
def test_audit_fails_for_empty_or_garbled_chunks(report, result, text, reason):
    bad = dataclasses.replace(result.chunks[0], text=text)

    audit = audit_chunks(report, [bad])

    assert audit.failures == [f"{bad.chunk_id}: {reason}" + (" characters" if text else "")]


def test_long_section_splits_at_paragraphs_and_continues_across_the_page_break(tmp_path):
    result = ingest_document(long_section_report(tmp_path / "findings.pdf"))

    assert result.audit.passed, result.audit.failures
    assert {chunk.section for chunk in result.chunks} == {"Findings"}
    assert all(len(chunk.text) <= 2000 for chunk in result.chunks)
    first, second = result.chunks
    assert (first.pdf_page, first.pdf_page_end) == (1, 1)
    assert (second.pdf_page, second.pdf_page_end) == (1, 2)
    assert second.chunk_id == "findings#p1-2"
    assert second.text.startswith("Region 3 forests")
    assert "Mangroves store large amounts of carbon" in second.text
