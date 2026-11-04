"""Ingest one PDF: parse it, cut it into chunks and audit them."""

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path

from askwri.ingest.acronyms import find_acronyms
from askwri.ingest.audit import AuditResult, audit_chunks
from askwri.ingest.chunks import Chunk, build_chunks
from askwri.ingest.labels import (
    DocumentLabels,
    chunk_label_fields,
    label_document,
    with_enrichment,
    with_year,
)
from askwri.ingest.model_labels import enrichment_from_text
from askwri.ingest.pdf import ParsedPdf, parse_pdf
from askwri.ingest.table_summary import summarize_tables
from askwri.ingest.wri_site import WriSite

# Sections a reader skims to label a document; the labeler reads them before the rest.
SUMMARY_SECTIONS = re.compile(
    r"summary|highlights|key (?:findings|messages|takeaways)|abstract|foreword|introduction"
    r"|conclusions?",
    re.IGNORECASE,
)
OUTLINE_CHARS = 3000  # the section list the labeler sees; a long report's would crowd the text


@dataclass(frozen=True)
class IngestResult:
    """One PDF's chunks, marked quotable or not, and the audit that decides if they're indexed."""

    chunks: list[Chunk]
    audit: AuditResult
    labels: DocumentLabels
    doc_id: str
    pdf_file: str  # the stored PDF a citation falls back to when there is no wri.org page


def ingest_document(pdf_path: Path, site: WriSite | None = None, client=None) -> IngestResult:
    """Turn one PDF into chunks, its labels, and the audit that gates indexing.

    Labels come from the wri.org page, and from the labeler model (`client`) where there is none.
    Their title (not the PDF's metadata title) is each chunk's `doc_title`.
    With no site, nothing is looked up; with no client, the model is never called and a document
    without a page is labelled "no page". The same model writes each table chunk's description,
    but only once the audit has passed, so a document that will not be indexed costs no calls.
    Once the audit has passed, the model also makes one enrichment call per document (topics,
    concepts, keywords, places, key findings, genre, coverage), added after WRI's own labels.
    An undated document takes its year from its folder ("2025/report.pdf"), and the acronyms
    its text defines are found by rule, with or without a client.
    A model error fails the document; with no client, table chunks have no description.
    """
    parsed = parse_pdf(pdf_path)
    title = _title(parsed, pdf_path)
    doc_id = doc_id_for(pdf_path)
    chunks = build_chunks(doc_id, title, parsed.blocks, parsed.printed_pages)
    audit = audit_chunks(pdf_path, chunks)
    unquotable = set(audit.unquotable)
    labels = with_year(label_document(pdf_path, title, site, client), pdf_path)
    labels = dataclasses.replace(
        labels, acronyms=find_acronyms("\n\n".join(chunk.text for chunk in chunks))
    )
    # The PDF's own title is often junk ("Aspose", "draft_v6.indd"); the page's or the
    # labeler's goes into every chunk's address, which is embedded.
    chunks = [dataclasses.replace(chunk, doc_title=labels.title) for chunk in chunks]
    if client and audit.passed:
        chunks = summarize_tables(client, chunks)
        reading = _enrichment_text(labels, chunks)
        labels = with_enrichment(labels, enrichment_from_text(client, pdf_path.name, reading))
    chunks = [
        dataclasses.replace(
            chunk, quotable=chunk.chunk_id not in unquotable, **chunk_label_fields(labels)
        )
        for chunk in chunks
    ]
    return IngestResult(
        chunks=chunks,
        audit=audit,
        labels=labels,
        doc_id=doc_id,
        pdf_file=pdf_path.name,
    )


def doc_id_for(pdf_path: Path) -> str:
    """A readable, stable document ID from the file name, e.g. "critical-minerals-india"."""
    return re.sub(r"[^a-z0-9]+", "-", pdf_path.stem.lower()).strip("-")


def _enrichment_text(labels: DocumentLabels, chunks: list[Chunk]) -> str:
    """What the labeler reads to enrich a document, most useful first.

    The title, wri.org abstract and tags, the outline (section paths), then the text of
    summary-like sections, then the rest in reading order. Chunks with a role (references,
    contents...) are left out. The labeler cuts it at ENRICH_CHARS.
    """
    body = [chunk for chunk in chunks if chunk.kind == "source_text" and chunk.role is None]
    first = [chunk for chunk in body if SUMMARY_SECTIONS.search(chunk.section)]
    rest = [chunk for chunk in body if not SUMMARY_SECTIONS.search(chunk.section)]
    outline = "\n".join(dict.fromkeys(chunk.section for chunk in chunks if chunk.section))
    head = [
        f"Title: {labels.title}",
        f"Abstract: {labels.abstract}" if labels.abstract else "",
        f"WRI tags: {', '.join(labels.tags)}" if labels.tags else "",
        f"Outline:\n{outline[:OUTLINE_CHARS]}" if outline else "",
        "Text:",
    ]
    return (
        "\n".join(line for line in head if line)
        + "\n"
        + "\n\n".join(chunk.text for chunk in first + rest)
    )


def _title(parsed: ParsedPdf, pdf_path: Path) -> str:
    """The PDF's metadata title, else its first top-level heading, else the file name."""
    if parsed.title:
        return parsed.title
    first_page = parsed.blocks[0].page if parsed.blocks else 0
    headings = [b for b in parsed.blocks if b.page == first_page and b.heading_level]
    if headings:
        return min(headings, key=lambda block: block.heading_level).text
    return pdf_path.stem
