"""Command line: ingest PDFs and write chunks with metadata sidecars."""

import argparse
import json
import sys
from pathlib import Path

from askwri.ingest.chunks import Chunk
from askwri.ingest.document import IngestResult, ingest_document
from askwri.ingest.labels import catalog_row
from askwri.ingest.wri_site import WriSite
from askwri.models import claude_client


def write_chunks(chunks: list[Chunk], out_dir: Path) -> None:
    """Write each chunk as <doc_id>/<p..>.txt plus a .metadata.json sidecar.

    The document's filterable labels (topic, year, tags, link) go into every sidecar; a label
    the document lacks is left out. This format is replaced by JSON Lines chunk records (#11).
    """
    for chunk in chunks:
        doc_dir = out_dir / chunk.doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        path = doc_dir / f"{chunk.chunk_id.split('#')[1]}.txt"
        path.write_text(chunk.indexed_text, encoding="utf-8")
        attributes = {
            "chunk_id": chunk.chunk_id,
            "seq": chunk.seq,
            "doc_id": chunk.doc_id,
            "doc_title": chunk.doc_title,
            "pdf_page": chunk.pdf_page,
            "pdf_page_end": chunk.pdf_page_end,
            "printed_page": chunk.printed_page,
            "printed_page_end": chunk.printed_page_end,
            "printed_page_fallback": chunk.printed_page_fallback,
            "section": chunk.section,
            "kind": chunk.kind,
            "quotable": chunk.quotable,
        }
        labelled = {
            "label_source": chunk.label_source,
            "link": chunk.link,
            "year": chunk.year,
            "topic": chunk.topic,
            "wri_type": chunk.wri_type,
            "tags": list(chunk.tags),
            "role": chunk.role,
            "number": chunk.number,
            "table_first_chunk": chunk.table_first_chunk,
            "description": chunk.description,
        }
        attributes |= {key: value for key, value in labelled.items() if value}
        path.with_name(f"{path.name}.metadata.json").write_text(
            json.dumps({"metadataAttributes": attributes}, ensure_ascii=False), encoding="utf-8"
        )


def write_catalog(results: list[IngestResult], out_dir: Path) -> None:
    """Write catalog.json: one row per document, for counting and listing questions."""
    # shortcut: local file - the catalog moves to S3 with the S3 ticket (#11)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [catalog_row(r.doc_id, r.pdf_file, r.labels) for r in results]
    (out_dir / "catalog.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class _ClientOnFirstUse:
    """The Bedrock Claude client, created the first time a document needs the labeler.

    Every document that passes the audit gets an enrichment call, so a run with any such
    document needs AWS credentials and a region.
    """

    def __init__(self):
        self._client = None

    def __getattr__(self, name):
        if self._client is None:
            self._client = claude_client()
        return getattr(self._client, name)


def main() -> int:
    """Ingest each PDF and write its chunks; a PDF that fails the audit writes nothing.

    Returns the exit code: 1 if any PDF failed the audit, else 0.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdfs", nargs="+", type=Path, help="PDF files to ingest")
    parser.add_argument("--out", type=Path, required=True, help="folder for chunk files")
    args = parser.parse_args()

    site = WriSite()
    client = _ClientOnFirstUse()
    failed = False
    passed: list[IngestResult] = []
    for pdf in args.pdfs:
        result = ingest_document(pdf, site, client)
        for page in result.audit.pages_without_text:
            print(f"{pdf.name}: page {page} has no text layer", file=sys.stderr)
        if not result.audit.passed:
            failed = True
            print(f"{pdf.name}: audit failed, nothing written", file=sys.stderr)
            for failure in result.audit.failures:
                print(f"  {failure}", file=sys.stderr)
            continue
        write_chunks(result.chunks, args.out)
        passed.append(result)
        print(
            f"{pdf.name}: {len(result.chunks)} chunks, "
            f"{len(result.audit.unquotable)} not quotable (re-ordered); "
            f"{result.pictures.summary}; "
            f"labels: {result.labels.label_source}, topic: {result.labels.topic or 'none'}"
        )
    write_catalog(passed, args.out)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
