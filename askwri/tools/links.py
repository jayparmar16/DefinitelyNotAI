"""links tool: which documents in the collection cite the given ones, and which they cite.

Event: {"doc_ids": [str, ...]}. Links come from the citations table (python -m askwri.links):
each is a real mention of one document's DOI, wri.org address or title in another's text.
"""

from askwri.tools.db import connect

SQL = """
SELECT c.src_doc_id, s.title AS src_title, s.year AS src_year, s.pdf_key AS src_pdf_key,
       c.dst_doc_id, d.title AS dst_title, d.year AS dst_year, d.pdf_key AS dst_pdf_key,
       c.relation, c.aspect, c.confidence, c.match_method, c.context_sentence, c.context_page
FROM citations c
JOIN documents s ON s.doc_id = c.src_doc_id
JOIN documents d ON d.doc_id = c.dst_doc_id
WHERE c.src_doc_id = ANY (%(doc_ids)s) OR c.dst_doc_id = ANY (%(doc_ids)s)
ORDER BY c.confidence DESC NULLS LAST
"""
CITED_BY = """
SELECT dst_doc_id AS doc_id, count(*) AS cited_by FROM citations
WHERE dst_doc_id = ANY (%(doc_ids)s) GROUP BY dst_doc_id
"""
MAX_DOCUMENTS = 25


def handler(event: dict, context) -> dict:
    """Return the citation links touching these documents and how often each is cited."""
    doc_ids = list(event.get("doc_ids") or [])[:MAX_DOCUMENTS]
    if not doc_ids:
        return {"links": [], "cited_by": {}}
    with connect() as connection:
        links = connection.execute(SQL, {"doc_ids": doc_ids}).fetchall()
        counts = connection.execute(CITED_BY, {"doc_ids": doc_ids}).fetchall()
    return {
        "links": links,
        "cited_by": {row["doc_id"]: row["cited_by"] for row in counts},
    }
