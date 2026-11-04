"""Chunk sizes and order, driven through synthetic PDFs built from headings and paragraphs."""

import re
from pathlib import Path

import pymupdf

from askwri.ingest.document import ingest_document

MIN_CHARS, MAX_CHARS = 400, 2000
LINE_WIDTH = 85  # characters per line at font size 10 in a 500-point-wide box, with margin


def sentence(n: int) -> str:
    """A sentence with an abbreviation and a decimal, which a naive splitter would cut at."""
    return f"The U.S. Department of Energy, e.g. in Washington, reported growth of 3.5 percent in item {n}. "


def paragraph(length: int, label: str) -> str:
    """A paragraph of about `length` characters, made of sentences numbered from the label."""
    sentences, n = [], 1
    while len(" ".join(sentences)) < length:
        sentences.append(f"{label} {sentence(n)}".strip() if n == 1 else sentence(n).strip())
        n += 1
    return " ".join(sentences)


def make_report(path: Path, items: list[tuple[str, str]]) -> Path:
    """A PDF with one heading ("h") or paragraph ("p") per item, top to bottom, over as many pages as needed."""
    doc = pymupdf.open()
    page = doc.new_page()
    top = 60
    for kind, text in items:
        height = 30 if kind == "h" else 12 * (len(text) // LINE_WIDTH + 2)
        if top + height > 780:
            page, top = doc.new_page(), 60
        if kind == "h":
            page.insert_text((50, top + 14), text, fontsize=15, fontname="hebo")
        else:
            leftover = page.insert_textbox(
                pymupdf.Rect(50, top, 550, top + height), text, fontsize=10
            )
            assert leftover >= 0, "synthetic paragraph did not fit its box"
        top += height + 12
    doc.set_metadata({"title": "Sizing Test"})
    doc.save(path)
    return path


def ingest(tmp_path: Path, items: list[tuple[str, str]]):
    result = ingest_document(make_report(tmp_path / "sizing-test.pdf", items))
    assert result.audit.passed, result.audit.failures
    return result


def test_short_lines_merge_within_a_section_but_never_across_a_heading(tmp_path):
    result = ingest(
        tmp_path,
        [
            ("h", "Credits"),
            ("p", "Alice Example, Bob Sample"),
            ("p", "Carol Person"),
            ("p", "Dan Name"),
            ("h", "Results"),
            ("p", paragraph(500, "Findings.")),
        ],
    )

    credits, results = result.chunks
    assert (credits.section, results.section) == ("Credits", "Results")
    assert credits.text == "Alice Example, Bob Sample\n\nCarol Person\n\nDan Name"
    assert len(credits.text) < MIN_CHARS  # the whole section is short, so it stays one short chunk
    assert "Alice" not in results.text


def test_a_short_paragraph_merges_with_the_next_one(tmp_path):
    result = ingest(
        tmp_path,
        [("h", "Summary"), ("p", "A short opening line."), ("p", paragraph(450, "Details."))],
    )

    (chunk,) = result.chunks
    assert chunk.text.startswith("A short opening line.\n\nDetails.")


def test_a_short_last_paragraph_takes_what_it_needs_from_the_chunk_before(tmp_path):
    result = ingest(
        tmp_path,
        [
            ("h", "Findings"),
            ("p", paragraph(1000, "First.")),
            ("p", paragraph(900, "Second.")),
            ("p", "Third, a brief closing paragraph with a few words."),
        ],
    )

    sizes = [len(chunk.text) for chunk in result.chunks]
    assert len(sizes) == 2
    assert all(MIN_CHARS <= size <= MAX_CHARS for size in sizes), sizes
    assert result.chunks[1].text.endswith("a few words.")
    assert "Second." in result.chunks[1].text


def test_an_overlong_paragraph_splits_at_sentences_not_at_abbreviations(tmp_path):
    long_paragraph = paragraph(5000, "Long.")

    result = ingest(tmp_path, [("h", "Findings"), ("p", long_paragraph)])

    texts = [chunk.text for chunk in result.chunks]
    assert len(texts) >= 3
    assert all(MIN_CHARS <= len(text) <= MAX_CHARS for text in texts)
    for text in texts:
        assert re.fullmatch(r"(Long\. )?The U\.S\. .* item \d+\.", text, re.DOTALL), text
    assert " ".join(texts) == long_paragraph
    assert len({(c.pdf_page, c.pdf_page_end) for c in result.chunks}) == 1  # all on one page


def test_a_single_sentence_longer_than_the_maximum_stays_whole(tmp_path):
    run_on = "A sentence that keeps going " + "and going " * 215 + "until it ends."
    assert len(run_on) > MAX_CHARS

    result = ingest(tmp_path, [("h", "Findings"), ("p", run_on)])

    (chunk,) = result.chunks
    assert chunk.text == run_on


def test_seq_is_contiguous_from_one_and_identical_across_runs(tmp_path):
    items = [
        ("h", "First"),
        ("p", paragraph(3000, "One.")),
        ("h", "Second"),
        ("p", "Tiny."),
        ("h", "Third"),
        ("p", paragraph(1500, "Three.")),
        ("p", paragraph(1500, "Four.")),
    ]
    pdf = make_report(tmp_path / "sizing-test.pdf", items)

    first, rerun = ingest_document(pdf), ingest_document(pdf)

    assert [chunk.seq for chunk in first.chunks] == list(range(1, len(first.chunks) + 1))
    assert [(c.seq, c.chunk_id, c.text) for c in rerun.chunks] == [
        (c.seq, c.chunk_id, c.text) for c in first.chunks
    ]
    assert first.chunks[0].chunk_id == "sizing-test#p1-1"
    assert len(first.chunks) >= 4
