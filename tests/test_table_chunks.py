"""Table chunks, driven through synthetic PDFs with ruled tables and the fake model client."""

from pathlib import Path

import pymupdf
import pytest

from askwri.ingest.document import ingest_document
from askwri.models import MODELS, ModelError
from tests.fake_claude import FakeClaude

PARAGRAPH = (
    "Forests store large amounts of carbon and support the livelihoods of many communities. "
    "Protecting them requires secure land rights, transparent monitoring and finance that "
    "reaches local groups. "
)
HEADER = ["Country", "Forest (Mha)", "Share (%)", "Change (%)"]


def data_rows(count: int, first: int = 1, suffix: str = "") -> list[list[str]]:
    """A header row, then `count` numeric rows named Country <first>, Country <first + 1>, ..."""
    return [HEADER] + [
        [f"Country {n}{suffix}", f"{n * 3.5:.1f}", f"{n * 2.1:.1f}", f"-{n * 0.4:.1f}"]
        for n in range(first, first + count)
    ]


def draw_table(
    page,
    top: float,
    rows: list[list[str]],
    row_height: float = 20,
    fontsize: float = 9,
    text_order: str = "",
) -> float:
    """Draw a ruled table with its top edge at `top`; returns the y of its bottom edge.

    The text layer lists rows top to bottom and cells left to right, unless `text_order` is
    "rows reversed" (header last) or "cells reversed" (each row right to left).
    """
    widths, left = (150, 110, 110, 110), 50
    edges = [left]
    for width in widths:
        edges.append(edges[-1] + width)
    bottom = top + len(rows) * row_height
    for n in range(len(rows) + 1):
        page.draw_line((left, top + n * row_height), (edges[-1], top + n * row_height), width=0.7)
    for x in edges:
        page.draw_line((x, top), (x, bottom), width=0.7)
    row_numbers = reversed(range(len(rows))) if text_order == "rows reversed" else range(len(rows))
    for r in row_numbers:
        row = rows[r]
        cells = reversed(list(enumerate(row))) if text_order == "cells reversed" else enumerate(row)
        for c, cell in cells:
            page.insert_text(
                (edges[c] + 3, top + (r + 1) * row_height - row_height / 4),
                cell,
                fontsize=fontsize,
                fontname="hebo" if r == 0 else "helv",
            )
    return bottom


def draw_paragraph(page, top: float, text: str) -> None:
    """Draw a 500-point-wide paragraph at `top`, failing the test if it does not fit."""
    assert page.insert_textbox(pymupdf.Rect(50, top, 550, top + 110), text, fontsize=10) >= 0


def save(doc: pymupdf.Document, path: Path, title: str) -> Path:
    doc.set_metadata({"title": title})
    doc.save(path)
    return path


def report_with_tables(path: Path) -> Path:
    """Page 1: Table 2 with Notes and Sources, its caption below them, then Table 3 under a heading.

    Page 2: Table 3 again, "(cont.)", then a heading over a grid of names.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 60), "Findings", fontsize=15, fontname="hebo")
    draw_paragraph(page, 70, PARAGRAPH * 2)
    bottom = draw_table(page, 190, data_rows(6))
    page.insert_text((50, bottom + 16), "Notes: Mha is million hectares.", fontsize=8)
    page.insert_text(
        (50, bottom + 36), "Sources: WRI analysis of national inventories.", fontsize=8
    )
    page.insert_text((50, bottom + 64), "Table 2 | Forest cover by country, 2020", fontsize=10)
    draw_paragraph(page, bottom + 90, (PARAGRAPH * 2).replace("Forests", "Peatlands"))
    top = bottom + 220
    page.insert_text((50, top), "Table 3 | Priority countries", fontsize=15, fontname="hebo")
    draw_table(page, top + 15, data_rows(3, first=10))
    second = doc.new_page()
    second.insert_text(
        (50, 60), "Table 3 | Priority countries (cont.)", fontsize=10, fontname="hebo"
    )
    bottom = draw_table(second, 75, data_rows(3, first=13))
    second.insert_text((50, bottom + 40), "Board of directors", fontsize=15, fontname="hebo")
    names = [
        ["Alice Smith", "Bob Jones", "Carol Wu", "Dan Lee"],
        ["Eve Adams", "Frank Hill", "Gina Cole", "Hal Ray"],
        ["Ian Fox", "Jane Roe", "Kim Lu", "Leo Park"],
    ]
    draw_table(second, bottom + 55, names)
    return save(doc, path, "Forest Cover")


def report_with_neighbouring_captions(path: Path) -> Path:
    """Two tables, each captioned above; the second caption is nearer the first table than its own."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 80), "Table 1 | Forest cover in 2020", fontsize=10, fontname="hebo")
    bottom = draw_table(page, 120, data_rows(4))
    page.insert_text(
        (50, bottom + 28), "Table 2 | Forest loss in 2021", fontsize=10, fontname="hebo"
    )
    draw_table(page, bottom + 62, data_rows(4, first=5))
    return save(doc, path, "Neighbours")


def report_with_one_table(path: Path, text_order: str) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Table 1 | Forest cover by country", fontsize=10, fontname="hebo")
    draw_table(page, 65, data_rows(5), text_order=text_order)
    return save(doc, path, "One Table")


def report_with_long_table(path: Path, caption: str = "Table 1 | Forest cover by country") -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    if caption:
        page.insert_text((50, 50), caption, fontsize=10, fontname="hebo")
    bottom = draw_table(page, 65, data_rows(46, suffix=" of the survey"), row_height=15, fontsize=8)
    page.insert_text((50, bottom + 16), "Source: WRI analysis.", fontsize=8)
    return save(doc, path, "Long Table")


def ingest(path: Path, *summaries: str):
    result = ingest_document(path, client=FakeClaude(*summaries))
    assert result.audit.passed, result.audit.failures
    return result


@pytest.fixture(scope="module")
def tables_pdf(tmp_path_factory) -> Path:
    return report_with_tables(tmp_path_factory.mktemp("pdf") / "forest-cover.pdf")


@pytest.fixture(scope="module")
def result(tables_pdf):
    return ingest(tables_pdf, *["Summary of a table."] * 5)


def by_number(result, number: str):
    return [c for c in result.chunks if c.number == number]


def test_table_is_a_chunk_with_rows_caption_notes_and_number(result):
    (table, *_) = by_number(result, "Table 2")

    assert table.kind == "table"
    assert table.quotable
    assert table.text.startswith("Table 2 | Forest cover by country, 2020\n\n|Country|")
    assert "|---|---|---|---|" in table.text
    assert "|Country 3|10.5|6.3|-1.2|" in table.text
    assert table.text.endswith(
        "Notes: Mha is million hectares.\n\nSources: WRI analysis of national inventories."
    )
    assert (table.pdf_page, table.pdf_page_end, table.section) == (1, 1, "Findings")


def test_a_table_caption_that_is_a_heading_is_not_a_section(result):
    assert {chunk.section for chunk in result.chunks} == {"Findings", "Board of directors"}


def test_the_text_around_a_table_is_separate_chunks_without_its_notes(result):
    text_chunks = [c for c in result.chunks if c.kind == "source_text" and c.pdf_page == 1]

    assert [c.text[:9] for c in text_chunks] == ["Forests s", "Peatlands"]
    assert all("Notes" not in c.text and "Sources" not in c.text for c in text_chunks)


def test_table_chunks_are_in_reading_order_with_contiguous_seq(result):
    assert [c.seq for c in result.chunks] == list(range(1, len(result.chunks) + 1))
    assert [c.kind for c in result.chunks][:4] == ["source_text", "table", "source_text", "table"]


def test_continued_table_links_to_its_first_part_and_records_both_pages(result):
    first, continued = by_number(result, "Table 3")

    assert first.table_first_chunk is None
    assert continued.table_first_chunk == first.chunk_id
    assert (first.pdf_page, continued.pdf_page) == (1, 2)
    assert continued.text.startswith("Table 3 | Priority countries (cont.)")


def test_a_grid_of_names_is_text_without_a_table_number(result):
    grid = [c for c in result.chunks if "Alice Smith" in c.text]

    assert [(c.kind, c.number) for c in grid] == [("source_text", None)]
    assert grid[0].section == "Board of directors"
    assert "|" not in grid[0].text


def test_nearest_caption_wins_but_a_caption_above_beats_a_slightly_nearer_one_below(tmp_path):
    chunks = ingest(
        report_with_neighbouring_captions(tmp_path / "neighbours.pdf"), "One.", "Two."
    ).chunks

    first, second = chunks
    assert (first.number, second.number) == ("Table 1", "Table 2")
    assert "Country 1|" in first.text
    assert "Country 5|" in second.text


def test_large_table_splits_by_rows_with_caption_and_header_repeated(tmp_path):
    chunks = ingest(report_with_long_table(tmp_path / "long-table.pdf"), *["Summary."] * 10).chunks

    assert len(chunks) > 1
    assert all(len(c.text) <= 2000 for c in chunks)
    assert {c.number for c in chunks} == {"Table 1"}
    assert [c.table_first_chunk for c in chunks] == [None] + [chunks[0].chunk_id] * (
        len(chunks) - 1
    )
    for chunk in chunks:
        lines = chunk.text.splitlines()
        assert lines[0] == "Table 1 | Forest cover by country"
        assert lines[2].startswith("|Country|Forest (Mha)|")
        assert lines[3] == "|---|---|---|---|"
    rows = [line for c in chunks for line in c.text.splitlines() if line.startswith("|Country ")]
    assert rows == [
        f"|Country {n} of the survey|{n * 3.5:.1f}|{n * 2.1:.1f}|-{n * 0.4:.1f}|"
        for n in range(1, 47)
    ]
    assert chunks[-1].text.endswith("Source: WRI analysis.")
    assert not any("Source" in c.text for c in chunks[:-1])


def test_pieces_of_a_table_without_a_number_still_point_at_the_first(tmp_path):
    chunks = ingest(
        report_with_long_table(tmp_path / "no-number.pdf", caption=""), *["S."] * 10
    ).chunks

    assert len(chunks) > 1
    assert {c.number for c in chunks} == {None}
    assert [c.table_first_chunk for c in chunks] == [None] + [chunks[0].chunk_id] * (
        len(chunks) - 1
    )


def test_rows_are_quotable_when_the_text_layer_lists_them_in_another_order(tmp_path):
    pdf = report_with_one_table(tmp_path / "rows-reversed.pdf", text_order="rows reversed")

    (table,) = ingest(pdf, "A table.").chunks

    assert table.quotable


def test_a_table_with_a_row_in_another_word_order_is_kept_but_not_quotable(tmp_path):
    pdf = report_with_one_table(tmp_path / "cells-reversed.pdf", text_order="cells reversed")

    (table,) = ingest(pdf, "A table.").chunks

    assert not table.quotable


def test_description_is_for_search_only(tables_pdf):
    client = FakeClaude(*["Forest cover by country in 2020."] * 5)

    result = ingest_document(tables_pdf, client=client)

    table = by_number(result, "Table 2")[0]
    assert table.description == "Forest cover by country in 2020."
    assert "Forest cover by country in 2020." not in table.text
    assert table.indexed_text.startswith(
        "Forest Cover › Findings\n\nForest cover by country in 2020.\n\n"
    )
    assert all(c.description == "" for c in result.chunks if c.kind == "source_text")
    assert len(client.requests) == sum(c.kind == "table" for c in result.chunks)
    request = client.requests[0]
    assert request["model"] == MODELS["labeler"]
    assert "|Country 3|10.5|6.3|-1.2|" in request["messages"][0]["content"][0]["text"]


def test_a_model_refusal_fails_the_document(tables_pdf):
    with pytest.raises(ModelError, match="forest-cover.*labeler call did not finish"):
        ingest_document(tables_pdf, client=FakeClaude({"stop_reason": "refusal"}))


def test_without_a_client_no_summaries_are_written(tables_pdf):
    result = ingest_document(tables_pdf)

    assert all(chunk.description == "" for chunk in result.chunks)
