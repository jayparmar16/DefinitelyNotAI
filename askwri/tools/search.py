"""search tool: hybrid vector + keyword search over WRI passages, then Bedrock reranking.

Event: {"query": str, "k": int, "year_from": int, "year_to": int, "include_undated": bool,
"pub_type": str, "topic": str, "country": str, "language": str, "doc_id": str}; only query is
required. doc_id searches inside one document (the research lens reads each paper this way).
A query that says "published in 2025" gets that year filter (the pipeline's search rule).
"""

import json
import os
import re

import boto3

from askwri.embed import embed
from askwri.tools.db import connect

CANDIDATES = 40  # per search method, before fusion
RERANK_POOL = 30  # fused candidates sent to the reranker
MAX_K = 20
RRF_K = 60  # reciprocal rank fusion constant: score = sum of 1 / (RRF_K + rank)
# Uncapped, one document's passages filled most of the pool (askwri.search, evaluation notes).
PER_DOCUMENT = 6
# Evidence-aware ranking: a small lift for WRI's most reviewed formats and a small discount for
# work in progress. Small enough to break near-ties, never to beat a clearly better passage.
TYPE_WEIGHTS = {"Report": 1.10, "Technical note": 1.05, "Working paper": 0.95}

# RFPs, newsletters and dataset change logs are in the corpus but aren't research: they are
# searched only when a type filter asks for one of them.
# Passages with a role (references, notes, contents, acknowledgements, about, abbreviations)
# support a document; they never answer. Topic, country and region match the pipeline's labels.
# Both searches apply the same document filters. Keyword terms are OR-ed: AND-ing every word of
# a question would rarely match anything. 'english' matches the pipeline's tsv (stemmed).
FILTERS = """
  AND c.role IS NULL
  AND (%(year_from)s::int IS NULL OR d.year >= %(year_from)s OR (%(include_undated)s AND d.year IS NULL))
  AND (%(year_to)s::int IS NULL OR d.year <= %(year_to)s OR (%(include_undated)s AND d.year IS NULL))
  AND (%(pub_type)s::text IS NULL OR d.pub_type ILIKE %(pub_type)s)
  AND (%(pub_type)s::text IS NOT NULL OR coalesce(d.pub_type, '') NOT IN ('RFP', 'Newsletter', 'Dataset documentation'))
  AND (%(topic)s::text IS NULL OR d.topic ILIKE %(topic)s OR %(topic)s ILIKE ANY (d.topics)
       OR %(topic)s ILIKE ANY (d.concepts) OR %(topic)s ILIKE ANY (d.tags))
  AND (%(country)s::text IS NULL OR %(country)s ILIKE ANY (d.countries)
       OR %(country)s ILIKE ANY (d.regions))
  AND (%(language)s::text IS NULL OR d.language = %(language)s)
  AND (%(doc_id)s::text IS NULL OR d.doc_id = %(doc_id)s)
"""

SQL = f"""
WITH q AS (
  SELECT CAST(%(embedding)s AS vector) AS e,
         replace(plainto_tsquery('english', %(keywords)s)::text, '&', '|')::tsquery AS t
),
vec AS (
  SELECT c.chunk_id, row_number() OVER (ORDER BY c.embedding <=> q.e) AS r
  FROM chunks c JOIN documents_v d USING (doc_id), q
  WHERE true {FILTERS}
  ORDER BY c.embedding <=> q.e LIMIT {CANDIDATES}
),
kw AS (
  SELECT c.chunk_id, row_number() OVER (ORDER BY ts_rank_cd(c.tsv, q.t) DESC) AS r
  FROM chunks c JOIN documents_v d USING (doc_id), q
  WHERE c.tsv @@ q.t {FILTERS}
  ORDER BY ts_rank_cd(c.tsv, q.t) DESC LIMIT {CANDIDATES}
),
fused AS (
  SELECT chunk_id, sum(1.0 / ({RRF_K} + r)) AS fused_score,
         bool_or(src = 'meaning') AS by_meaning, bool_or(src = 'keyword') AS by_keyword
  FROM (SELECT chunk_id, r, 'meaning' AS src FROM vec
        UNION ALL SELECT chunk_id, r, 'keyword' FROM kw) ranked
  GROUP BY chunk_id
),
capped AS (
  SELECT f.*, row_number() OVER (PARTITION BY c.doc_id ORDER BY f.fused_score DESC) AS in_document
  FROM fused f JOIN chunks c USING (chunk_id)
)
SELECT f.fused_score, f.by_meaning, f.by_keyword,
       c.chunk_id, c.doc_id, c.page, c.page_end, c.printed_page, c.printed_page_end, c.section,
       c.kind, c.quotable, c.address, c.content, c.description,
       ts_headline('english', c.content, (SELECT t FROM q),
                   'MaxFragments=0, StartSel=«, StopSel=»') AS matched,
       d.title, d.url, d.doi, d.year, d.date_source, d.date_confidence, d.pub_type, d.office,
       d.topic, d.label_source, d.language, d.pdf_key, d.topics, d.regions, d.abstract
FROM capped f JOIN chunks_v c USING (chunk_id) JOIN documents_v d USING (doc_id)
WHERE f.in_document <= {PER_DOCUMENT}
ORDER BY f.fused_score DESC
LIMIT {RERANK_POOL}
"""


# Same rule as askwri.search.publication_years (the tools Lambda doesn't ship that module's
# model client); tests/test_tools.py checks the two agree. Only a publication phrase: "investment
# in 2025" is about events in 2025, and documents published in 2026 cover them.
PUBLISHED = re.compile(
    r"\b(?:published|publish|released)\s+(?:"
    r"(?:in|during)\s+(?P<year>20\d\d)"
    r"|(?:between|from)\s+(?P<start>20\d\d)\s+(?:and|to)\s+(?P<end>20\d\d)"
    r"|(?:since|after)\s+(?P<since>20\d\d))\b",
    re.IGNORECASE,
)


def publication_years(question: str) -> tuple[int | None, int | None, str]:
    """The publication years a query asks for, and the query without that phrase (which would
    otherwise match most documents in keyword search)."""
    match = PUBLISHED.search(question)
    if match is None:
        return None, None, question
    if match["year"]:
        start = end = int(match["year"])
    elif match["since"]:
        start, end = int(match["since"]), None
    else:
        start, end = int(match["start"]), int(match["end"])
    rest = " ".join((question[: match.start()] + question[match.end() :]).split())
    return start, end, rest


def search_parameters(event: dict) -> dict:
    """Validate the event and return SQL parameters (filters left out are None). A query that
    names publication years gets them as filters unless the event already has year filters."""
    query = (event.get("query") or "").strip()
    if not query:
        raise ValueError("search needs a non-empty 'query'")
    year_from, year_to, keywords = event.get("year_from"), event.get("year_to"), query
    if year_from is None and year_to is None:
        year_from, year_to, keywords = publication_years(query)
        # An explicit year excludes undated documents, as the pipeline's search does.
        if year_from is not None:
            event = {**event, "include_undated": False}
    # The embedding and the reranker keep the whole query; keyword search drops the year phrase.
    return {
        "query": query,
        "keywords": keywords or query,
        "year_from": year_from,
        "year_to": year_to,
        "include_undated": event.get("include_undated", True),
        "pub_type": event.get("pub_type"),
        "topic": event.get("topic"),
        "country": event.get("country"),
        "language": event.get("language"),
        "doc_id": event.get("doc_id"),
    }


def matched_terms(headline: str) -> list[str]:
    """Words keyword search matched, from ts_headline's «marked» output, without repeats."""
    terms = []
    for part in headline.split("«")[1:]:
        term = part.split("»", 1)[0].strip()
        if term and term.lower() not in (t.lower() for t in terms):
            terms.append(term)
    return terms


def by_evidence_weight(ranked: list[tuple[dict, float]], k: int) -> list[tuple[dict, float]]:
    """The k best passages after weighting rerank scores by publication type. Scores are
    returned unweighted: the agent's evidence threshold judges relevance, not format."""
    weighted = sorted(
        ranked, key=lambda pair: pair[1] * TYPE_WEIGHTS.get(pair[0]["pub_type"], 1.0), reverse=True
    )
    return weighted[:k]


def to_result(row: dict, relevance: float) -> dict:
    """One search hit as the agent sees it: the passage, its citation fields and why it matched."""
    return {
        "chunk_id": row["chunk_id"],
        "doc_id": row["doc_id"],
        "title": row["title"],
        "url": row["url"],
        "doi": row["doi"],
        "year": row["year"],
        "date_confidence": row["date_confidence"],
        "pub_type": row["pub_type"],
        "office": row["office"],
        "topic": row["topic"],
        "topics": row["topics"] or [],
        "regions": row["regions"] or [],
        "abstract": row["abstract"],  # WRI's own words from wri.org, for the source card
        "language": row["language"],
        "pdf_key": row["pdf_key"],  # stored PDF in the corpus bucket, for download links
        "page": row["page"],
        "printed_page": row["printed_page"],
        "section": row["section"],
        "kind": row["kind"],
        "quotable": row["quotable"],
        "passage": row["content"],
        "relevance": round(relevance, 4),
        "why": {
            "by_meaning": row["by_meaning"],
            "by_keyword": row["by_keyword"],
            "matched_terms": matched_terms(row["matched"]) if row["by_keyword"] else [],
            "date_source": row["date_source"],
            "label_source": row["label_source"],
            "type_weight": TYPE_WEIGHTS.get(row["pub_type"], 1.0),
        },
    }


def rerank(query: str, rows: list[dict], k: int, client=None) -> list[tuple[dict, float]]:
    """Reorder rows with the Bedrock rerank model (ASKWRI_RERANK_MODEL_ARN); keep the top k
    (all rows when the caller weights them afterwards)."""
    client = client or boto3.client("bedrock-agent-runtime")
    response = client.rerank(
        queries=[{"type": "TEXT", "textQuery": {"text": query}}],
        sources=[
            {
                "type": "INLINE",
                "inlineDocumentSource": {
                    "type": "TEXT",
                    "textDocument": {
                        "text": "\n\n".join(
                            part
                            for part in (row["address"], row.get("description"), row["content"])
                            if part
                        )
                    },
                },
            }
            for row in rows
        ],
        rerankingConfiguration={
            "type": "BEDROCK_RERANKING_MODEL",
            "bedrockRerankingConfiguration": {
                "numberOfResults": k,
                "modelConfiguration": {"modelArn": os.environ["ASKWRI_RERANK_MODEL_ARN"]},
            },
        },
    )
    return [(rows[r["index"]], r["relevanceScore"]) for r in response["results"]]


def handler(event: dict, context) -> dict:
    """Return the k most relevant passages (default 8) with citation fields and match reasons."""
    params = search_parameters(event)
    k = min(int(event.get("k", 8)), MAX_K)
    params["embedding"] = json.dumps(embed([params["query"]])[0])
    with connect() as connection:
        rows = connection.execute(SQL, params).fetchall()
    if not rows:
        return {"query": params["query"], "results": []}
    ranked = by_evidence_weight(rerank(params["query"], rows, len(rows)), k)
    return {"query": params["query"], "results": [to_result(row, score) for row, score in ranked]}
