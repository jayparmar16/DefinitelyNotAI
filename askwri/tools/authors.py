"""authors tool: the public authors of cited documents, as printed on wri.org or in the PDF.

Event: {"doc_ids": [str, ...]}.
"""

from askwri.tools.db import connect

SQL = """
SELECT doc_id, title, year, authors FROM documents
WHERE doc_id = ANY (%(doc_ids)s) ORDER BY year DESC NULLS LAST, title
"""
MAX_DOCUMENTS = 25


def people(documents: list[dict]) -> list[dict]:
    """Each author once, with the documents they wrote, most prolific first."""
    by_author: dict[str, list[str]] = {}
    for document in documents:
        for author in document["authors"]:
            by_author.setdefault(author, []).append(document["doc_id"])
    return [
        {"name": name, "doc_ids": doc_ids}
        for name, doc_ids in sorted(by_author.items(), key=lambda item: (-len(item[1]), item[0]))
    ]


def handler(event: dict, context) -> dict:
    """Return each document's authors and the people across them; public authorship only."""
    doc_ids = list(event.get("doc_ids") or [])[:MAX_DOCUMENTS]
    if not doc_ids:
        raise ValueError("authors needs 'doc_ids'")
    with connect() as connection:
        documents = connection.execute(SQL, {"doc_ids": doc_ids}).fetchall()
    return {"documents": documents, "people": people(documents)}
