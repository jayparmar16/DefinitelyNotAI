"""Citation audit: check every chunk against the PDF's own text layer before it is indexed."""

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from askwri.ingest.chunks import Chunk
from askwri.ingest.text import comparable, missing_words


@dataclass(frozen=True)
class AuditResult:
    """Failures block indexing. Unquotable chunks are indexed but may never be quoted verbatim."""

    failures: list[str]
    unquotable: list[str]  # chunk IDs whose words are on the page, but not in this order
    pages_without_text: list[int]

    @property
    def passed(self) -> bool:
        return not self.failures


def audit_chunks(pdf_path: Path, chunks: list[Chunk]) -> AuditResult:
    """Check each chunk against the plain-text layer of the pages it claims.

    A chunk fails if it is empty, mostly non-text, claims pages outside the PDF, has words that
    are not on its pages, or (when it crosses a page break) does not start on its first page
    and end on its last. A chunk whose words are all on its pages, but where some paragraph
    is not a contiguous run of one page's text, is unquotable: the layout model re-ordered it
    (diagram labels, a pull quote overlapping a paragraph), so it may be cited by page but not
    quoted. In a table chunk each row is checked on its own, since a text layer often reads a
    table column by column and no table is one run. A picture chunk is checked by its caption
    alone, never by its description, and a picture with no caption is not checked. Matching ignores case, whitespace,
    punctuation, line-end hyphens and ligatures.
    """
    with pymupdf.open(pdf_path) as doc:
        page_texts = [page.get_text() for page in doc]
    failures, unquotable = [], []
    for chunk in chunks:
        if chunk.figure and not chunk.text:
            continue
        paragraphs = [p for p in chunk.text.split("\n\n") if p.strip()]
        if not 1 <= chunk.pdf_page <= chunk.pdf_page_end <= len(page_texts):
            failures.append(f"{chunk.chunk_id}: claims pages outside the PDF")
            continue
        texts = page_texts[chunk.pdf_page - 1 : chunk.pdf_page_end]
        if not paragraphs:
            failures.append(f"{chunk.chunk_id}: empty chunk")
        elif _mostly_non_text(chunk.text):
            failures.append(f"{chunk.chunk_id}: mostly non-text characters")
        elif reason := _not_on_claimed_pages(chunk, paragraphs, texts):
            failures.append(f"{chunk.chunk_id}: {reason}")
        elif not _is_verbatim(chunk, paragraphs, texts):
            unquotable.append(chunk.chunk_id)
    return AuditResult(
        failures=failures,
        unquotable=unquotable,
        pages_without_text=[n for n, text in enumerate(page_texts, start=1) if not text.strip()],
    )


def _is_verbatim(chunk: Chunk, paragraphs: list[str], texts: list[str]) -> bool:
    """Whether every paragraph (every line, for a table) is a contiguous run of one page's text."""
    units = (
        [line for p in paragraphs for line in p.splitlines()]
        if chunk.kind == "table"
        else paragraphs
    )
    runs = [comparable(t) for t in texts]
    return all(any(comparable(unit) in run for run in runs) for unit in units)


def _not_on_claimed_pages(chunk: Chunk, paragraphs: list[str], texts: list[str]) -> str | None:
    """Why the chunk's text is not on the pages it claims, or None if it is.

    Every word must be on the claimed pages together. A chunk that crosses a page break must
    also have its first paragraph on its first page and its last on its last, so an
    overstated page range is caught.
    """
    claimed = (
        f"page {chunk.pdf_page}"
        if chunk.pdf_page == chunk.pdf_page_end
        else f"pages {chunk.pdf_page}-{chunk.pdf_page_end}"
    )
    if missing := missing_words(chunk.text, "\n".join(texts)):
        return f"passage not found on {claimed}; missing words: {', '.join(missing[:5])}"
    if missing_words(paragraphs[0], texts[0]):
        return f"first passage not found on page {chunk.pdf_page}"
    if missing_words(paragraphs[-1], texts[-1]):
        return f"last passage not found on page {chunk.pdf_page_end}"
    return None


def _mostly_non_text(text: str) -> bool:
    text = re.sub(r"\||-{3,}", "", text)  # Markdown table syntax isn't garble
    visible = [char for char in text if not char.isspace()]
    return sum(char.isalnum() for char in visible) < len(visible) / 2
