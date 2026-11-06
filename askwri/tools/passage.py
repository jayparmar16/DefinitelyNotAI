"""get_passage tool: one passage with its citation fields, plus neighbouring passages for context.

Event: {"chunk_id": str, "neighbours": int (0-2, default 1)}.
"""

from askwri.tools.db import connect

SQL = """
SELECT c.chunk_id, c.seq, c.page, c.page_end, c.printed_page, c.printed_page_end, c.section,
       c.kind, c.quotable, c.content, d.doc_id, d.title, d.url, d.doi, d.year,
       d.date_confidence, d.pub_type, d.office, d.authors, d.language
FROM chunks_v c JOIN documents_v d USING (doc_id)
WHERE c.doc_id = (SELECT doc_id FROM chunks WHERE chunk_id = %(chunk_id)s)
  AND c.seq BETWEEN (SELECT seq FROM chunks WHERE chunk_id = %(chunk_id)s) - %(n)s
                AND (SELECT seq FROM chunks WHERE chunk_id = %(chunk_id)s) + %(n)s
ORDER BY c.seq
"""


def split_rows(rows: list[dict], chunk_id: str) -> dict:
    """Shape rows into the passage asked for, its document, and the passages around it."""
    target = next((row for row in rows if row["chunk_id"] == chunk_id), None)
    if target is None:
        raise ValueError(f"no passage with chunk_id {chunk_id!r}")
    document_fields = (
        "doc_id",
        "title",
        "url",
        "doi",
        "year",
        "date_confidence",
        "pub_type",
        "office",
        "authors",
        "language",
    )
    passage_fields = (
        "chunk_id",
        "page",
        "page_end",
        "printed_page",
        "printed_page_end",
        "section",
        "kind",
        "quotable",
        "content",
    )
    return {
        "passage": {field: target[field] for field in passage_fields},
        "document": {field: target[field] for field in document_fields},
        "before": [row["content"] for row in rows if row["seq"] < target["seq"]],
        "after": [row["content"] for row in rows if row["seq"] > target["seq"]],
    }


def handler(event: dict, context) -> dict:
    """Return the passage, its document's citation fields and up to 2 neighbours each side."""
    chunk_id = event["chunk_id"]
    neighbours = max(0, min(int(event.get("neighbours", 1)), 2))
    with connect() as connection:
        rows = connection.execute(SQL, {"chunk_id": chunk_id, "n": neighbours}).fetchall()
    return split_rows(rows, chunk_id)
