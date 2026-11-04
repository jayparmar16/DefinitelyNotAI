"""Printed page numbers, page ranges and running headers/footers, driven through ingest_document."""

import dataclasses
import json
from pathlib import Path

import pymupdf

from askwri.ingest.__main__ import write_chunks
from askwri.ingest.audit import audit_chunks
from askwri.ingest.document import ingest_document

PARAGRAPH = (
    "Forests store large amounts of carbon and support the livelihoods of many communities. "
    "Protecting them requires secure land rights, transparent monitoring and finance that "
    "reaches local groups. "
)
HEADER = "Annual Policy Digest"


def add_page(doc: pymupdf.Document, heading: str, body: str, footer: str = "") -> None:
    """A page with a heading, one paragraph, and optionally a running header and footer."""
    page = doc.new_page()
    page.insert_text((50, 100), heading, fontsize=15, fontname="hebo")
    page.insert_textbox(pymupdf.Rect(50, 120, 550, 300), body * 3, fontsize=10)
    if footer:
        page.insert_text((50, 40), HEADER, fontsize=8)
        page.insert_text((50, 810), footer, fontsize=8)


def front_matter_report(path: Path) -> Path:
    """Two Roman-numeral front matter pages, then two pages numbered 1 and 2 by page labels."""
    doc = pymupdf.open()
    for heading in ("Preface", "Foreword", "Chapter One", "Chapter Two"):
        add_page(doc, heading, PARAGRAPH.replace("Forests", f"{heading} forests"))
    doc.set_page_labels(
        [
            {"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1},
            {"startpage": 2, "prefix": "", "style": "D", "firstpagenum": 1},
        ]
    )
    doc.save(path)
    return path


def running_header_report(path: Path, numbered: bool = True) -> Path:
    """An unnumbered cover, then five pages whose footers print 1 to 5 beside running text."""
    doc = pymupdf.open()
    add_page(doc, "Cover Story", PARAGRAPH)
    for n in range(1, 6):
        footer = f"Working Paper  |  January 2025  |  {n}" if numbered else "Working Paper"
        add_page(doc, f"Part {n}", PARAGRAPH.replace("Forests", f"Part {n} forests"), footer)
    doc.save(path)
    return path


def test_page_labels_give_roman_numeral_front_matter_and_restarted_numbering(tmp_path):
    result = ingest_document(front_matter_report(tmp_path / "labelled.pdf"))

    assert result.audit.passed, result.audit.failures
    assert [(c.pdf_page, c.printed_page) for c in result.chunks] == [
        (1, "i"),
        (2, "ii"),
        (3, "1"),
        (4, "2"),
    ]
    assert not any(chunk.printed_page_fallback for chunk in result.chunks)


def test_printed_page_is_read_from_the_footer_when_the_pdf_has_no_labels(tmp_path):
    result = ingest_document(running_header_report(tmp_path / "footers.pdf"))

    by_page = {chunk.pdf_page: chunk for chunk in result.chunks}
    assert [by_page[n].printed_page for n in range(2, 7)] == ["1", "2", "3", "4", "5"]
    assert not any(by_page[n].printed_page_fallback for n in range(2, 7))
    assert (by_page[1].printed_page, by_page[1].printed_page_fallback) == ("1", True)


def test_printed_page_falls_back_to_the_pdf_page_and_is_flagged(tmp_path):
    result = ingest_document(running_header_report(tmp_path / "bare.pdf", numbered=False))

    assert [(c.pdf_page, c.printed_page) for c in result.chunks] == [
        (n, str(n)) for n in range(1, 7)
    ]
    assert all(chunk.printed_page_fallback for chunk in result.chunks)


def test_running_headers_and_footers_appear_in_no_chunk(tmp_path):
    result = ingest_document(running_header_report(tmp_path / "footers.pdf"))

    assert result.chunks
    for chunk in result.chunks:
        assert HEADER not in chunk.text
        assert "Working Paper" not in chunk.text
        assert "January 2025" not in chunk.text


def continuing_section_report(path: Path) -> Path:
    """Page 1 (printed vi) ends mid-section and page 2 (printed vii) continues it."""
    doc = pymupdf.open()
    first = doc.new_page()
    first.insert_text((50, 70), "Findings", fontsize=15, fontname="hebo")
    first.insert_textbox(pymupdf.Rect(50, 90, 550, 260), PARAGRAPH * 3, fontsize=10)
    first.insert_textbox(
        pymupdf.Rect(50, 640, 550, 810),
        (PARAGRAPH * 3).replace("Forests", "Peatlands"),
        fontsize=10,
    )
    second = doc.new_page()
    second.insert_textbox(
        pymupdf.Rect(50, 70, 550, 240), (PARAGRAPH * 3).replace("Forests", "Mangroves"), fontsize=10
    )
    doc.set_page_labels([{"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 6}])
    doc.save(path)
    return path


def test_a_chunk_crossing_a_page_break_records_both_page_ranges(tmp_path):
    result = ingest_document(continuing_section_report(tmp_path / "continuing.pdf"))

    assert result.audit.passed, result.audit.failures
    (chunk,) = result.chunks
    assert chunk.chunk_id == "continuing#p1-1"
    assert (chunk.pdf_page, chunk.pdf_page_end) == (1, 2)
    assert (chunk.printed_page, chunk.printed_page_end) == ("vi", "vii")
    assert "Peatlands" in chunk.text
    assert "Mangroves" in chunk.text


def test_audit_checks_a_spanning_chunk_against_both_pages(tmp_path):
    pdf = continuing_section_report(tmp_path / "continuing.pdf")
    (chunk,) = ingest_document(pdf).chunks

    only_first = dataclasses.replace(chunk, pdf_page_end=1)
    only_second = dataclasses.replace(chunk, pdf_page=2)
    overstated = dataclasses.replace(
        chunk, text=chunk.text.split("\n\n")[0], pdf_page=1, pdf_page_end=2
    )

    assert audit_chunks(pdf, [chunk]).passed
    assert "passage not found on page 1" in audit_chunks(pdf, [only_first]).failures[0]
    assert "passage not found on page 2" in audit_chunks(pdf, [only_second]).failures[0]
    assert audit_chunks(pdf, [overstated]).failures == [
        f"{chunk.chunk_id}: last passage not found on page 2"
    ]


def test_sidecar_carries_page_ranges_for_filtering(tmp_path):
    result = ingest_document(continuing_section_report(tmp_path / "continuing.pdf"))

    write_chunks(result.chunks, tmp_path / "out")

    sidecar = tmp_path / "out" / "continuing" / "p1-1.txt.metadata.json"
    attributes = json.loads(sidecar.read_text())["metadataAttributes"]
    assert (attributes["pdf_page"], attributes["pdf_page_end"]) == (1, 2)
    assert (attributes["printed_page"], attributes["printed_page_end"]) == ("vi", "vii")
    assert attributes["printed_page_fallback"] is False
