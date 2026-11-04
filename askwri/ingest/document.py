"""Ingest one PDF: parse it, cut it into chunks and audit them."""

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path

from askwri.ingest.audit import AuditResult, audit_chunks
from askwri.ingest.chunks import Chunk, build_chunks
from askwri.ingest.labels import DocumentLabels, chunk_label_fields, label_document
from askwri.ingest.pdf import ParsedPdf, parse_pdf
from askwri.ingest.table_summary import summarize_tables
from askwri.ingest.wri_site import WriSite


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
    With no site, nothing is looked up; with no client, the model is never called and a document
    without a page is labelled "no page". The same model writes each table chunk's description,
    but only once the audit has passed, so a document that will not be indexed costs no calls.
    A model error fails the document; with no client, table chunks have no description.
    """
    parsed = parse_pdf(pdf_path)
    title = _title(parsed, pdf_path)
    doc_id = doc_id_for(pdf_path)
    chunks = build_chunks(doc_id, title, parsed.blocks, parsed.printed_pages)
    audit = audit_chunks(pdf_path, chunks)
    if client and audit.passed:
        chunks = summarize_tables(client, chunks)
    unquotable = set(audit.unquotable)
    labels = label_document(pdf_path, title, site, client)
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


def _title(parsed: ParsedPdf, pdf_path: Path) -> str:
    """The PDF's metadata title, else its first top-level heading, else the file name."""
    if parsed.title:
        return parsed.title
    first_page = parsed.blocks[0].page if parsed.blocks else 0
    headings = [b for b in parsed.blocks if b.page == first_page and b.heading_level]
    if headings:
        return min(headings, key=lambda block: block.heading_level).text
    return pdf_path.stem
