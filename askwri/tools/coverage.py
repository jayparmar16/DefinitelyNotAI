"""coverage tool: document counts by topic, concept, region, country, genre, year, type or
language, for gap analysis.

Event: {"dimension": str, "topic": str (optional filter), "country": str (optional filter),
"year": int (optional filter)}. Topics, concepts, regions and genres are the ingestion
pipeline's labels (askwri/ingest/vocabulary.py).
Counts describe the indexed collection only, and every result says so.
"""

from askwri.tools.db import connect

# Dimension name -> SQL expression yielding one value per document (arrays are unnested).
DIMENSIONS = {
    # Every topic a document covers (at most two); documents loaded before that keep one.
    "topic": "unnest(coalesce(nullif(d.topics, '{}'), ARRAY[d.topic]))",
    "concept": "unnest(d.concepts)",
    "region": "unnest(d.regions)",
    "genre": "d.genre",
    "tag": "unnest(d.tags)",
    "country": "unnest(d.countries)",
    "year": "d.year::text",
    "pub_type": "d.pub_type",
    "language": "d.language",
}

FILTER = """
WHERE (%(topic)s::text IS NULL OR d.topic ILIKE %(topic)s OR %(topic)s ILIKE ANY (d.topics)
       OR %(topic)s ILIKE ANY (d.concepts) OR %(topic)s ILIKE ANY (d.tags))
  AND (%(country)s::text IS NULL OR %(country)s ILIKE ANY (d.countries)
       OR %(country)s ILIKE ANY (d.regions))
  AND (%(year)s::int IS NULL OR d.year = %(year)s)
"""


def coverage_sql(dimension: str) -> str:
    """SQL counting documents per value of one dimension; refuses unknown dimensions."""
    if dimension not in DIMENSIONS:
        raise ValueError(f"dimension must be one of {sorted(DIMENSIONS)}, not {dimension!r}")
    return f"""
    SELECT coalesce(value, 'unknown') AS value, count(DISTINCT doc_id) AS documents
    FROM (SELECT d.doc_id, {DIMENSIONS[dimension]} AS value FROM documents_v d {FILTER}) v
    GROUP BY 1 ORDER BY documents DESC, value
    """


def handler(event: dict, context) -> dict:
    """Return counts per value plus the collection size, so gaps are stated against the sample."""
    dimension = event.get("dimension", "")
    params = {
        "topic": event.get("topic"),
        "country": event.get("country"),
        "year": event.get("year"),
    }
    with connect() as connection:
        counts = connection.execute(coverage_sql(dimension), params).fetchall()
        total = connection.execute(f"SELECT count(*) AS n FROM documents_v d {FILTER}", params)
        documents = total.fetchone()["n"]
        collection = connection.execute("SELECT count(*) AS n FROM documents").fetchone()["n"]
    return {
        "dimension": dimension,
        "counts": counts,
        "documents_matching_filters": documents,
        "scope": f"Based on the {collection} documents indexed in AskWRI, not WRI's full library.",
    }
