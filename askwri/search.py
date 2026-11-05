"""Hybrid passage search over Aurora: meaning + keyword search, fused, reranked, with neighbours.

Usage: `uv run python -m askwri.search "question" [--topic X] [--year-from N]`.
Needs AWS credentials in the environment; reads through the RDS Data API (no VPC access).
"""

import argparse
import json
import os
import re
import sys
from functools import cache

import boto3
from botocore.config import Config

from askwri.models import MODELS

CLUSTER = "askwri-db"
SECRET = "askwri/db"
# ASKWRI_DATABASE picks another database in the cluster, e.g. for an experiment beside the demo.
DATABASE = os.environ.get("ASKWRI_DATABASE", "askwri")
CANDIDATES = 25  # after fusion and the per-document cap: what the reranker sees
POOL = 100  # per ranking (meaning, keyword): wide enough that the cap still leaves CANDIDATES
# Chunks of one document among the candidates. Uncapped, one document's chunks took all 25
# places for most evaluation questions (1.5 documents per answer on average).
PER_DOCUMENT = 6
RESULTS = 10
# Rerank relevance below this is not an answer. On the evaluation set (python -m
# evals.rerankers), passages judged off topic scored at most 0.003 and the unanswerable
# questions' best candidates at most 0.006, while 0.05 dropped 9 of 80 passages that help.
MIN_RELEVANCE = 0.02
RRF_K = 60  # reciprocal rank fusion constant
# The first query after an Aurora auto-pause can take 30 s or more.
SLOW_START = Config(connect_timeout=90, read_timeout=90, retries={"max_attempts": 3})

COLUMNS = """c.chunk_id, c.doc_id, d.title, coalesce(d.url, d.pdf_key) AS link,
  c.pdf_page, c.pdf_page_end, c.printed_page, c.printed_page_end, c.section, c.kind,
  c.quotable, c.content, c.description, c.number, c.figure_key"""
# Chunks with a role (references, notes, contents, ...) support a document; they never answer.
FILTERS = """c.role IS NULL
  AND (CAST(:year_from AS int) IS NULL OR d.year >= CAST(:year_from AS int))
  AND (CAST(:year_to AS int) IS NULL OR d.year <= CAST(:year_to AS int))
  AND (CAST(:topic AS text) IS NULL OR d.topic = CAST(:topic AS text))
  AND (CAST(:doc_type AS text) IS NULL OR d.doc_type = CAST(:doc_type AS text))
  AND (CAST(:country AS text) IS NULL OR CAST(:country AS text) = ANY(d.countries))"""
# "published in 2025", "what did WRI publish in 2024", "published between 2024 and 2025",
# "published since 2024". Only a publication phrase: "investment in 2025" is about events in
# 2025, and documents published in 2026 cover them.
PUBLISHED = re.compile(
    r"\b(?:published|publish|released)\s+(?:"
    r"(?:in|during)\s+(?P<year>20\d\d)"
    r"|(?:between|from)\s+(?P<start>20\d\d)\s+(?:and|to)\s+(?P<end>20\d\d)"
    r"|(?:since|after)\s+(?P<since>20\d\d))\b",
    re.IGNORECASE,
)
RANK = "ts_rank(c.tsv, websearch_to_tsquery('english', :q))"
HYBRID_SQL = f"""
WITH meaning AS (
  SELECT c.chunk_id, row_number() OVER (ORDER BY c.embedding <=> CAST(:vec AS vector)) AS r
  FROM chunks c JOIN documents d USING (doc_id)
  WHERE {FILTERS}
  ORDER BY c.embedding <=> CAST(:vec AS vector) LIMIT {POOL}),
keyword AS (
  SELECT c.chunk_id, row_number() OVER (ORDER BY {RANK} DESC) AS r
  FROM chunks c JOIN documents d USING (doc_id)
  WHERE c.tsv @@ websearch_to_tsquery('english', :q) AND {FILTERS}
  ORDER BY {RANK} DESC LIMIT {POOL}),
fused AS (
  SELECT x.chunk_id, sum(1.0 / ({RRF_K} + x.r)) AS fused
  FROM (SELECT * FROM meaning UNION ALL SELECT * FROM keyword) x GROUP BY x.chunk_id),
capped AS (
  SELECT f.chunk_id, f.fused,
    row_number() OVER (PARTITION BY c.doc_id ORDER BY f.fused DESC) AS in_document
  FROM fused f JOIN chunks c USING (chunk_id))
SELECT {COLUMNS}, k.fused
FROM capped k JOIN chunks c USING (chunk_id) JOIN documents d USING (doc_id)
WHERE k.in_document <= {PER_DOCUMENT}
ORDER BY k.fused DESC LIMIT {CANDIDATES}
"""
CITATION_KEYS = (
    "chunk_id", "doc_id", "title", "link", "pdf_page", "pdf_page_end", "printed_page",
    "printed_page_end", "section", "kind", "quotable", "content", "description", "number",
    "figure_key",
)  # fmt: skip


@cache
def _aws() -> dict:
    """Clients (with slow-start timeouts) and the Data API target; built once per process."""
    cluster = boto3.client("rds", config=SLOW_START).describe_db_clusters(
        DBClusterIdentifier=CLUSTER
    )["DBClusters"][0]["DBClusterArn"]
    secret = boto3.client("secretsmanager", config=SLOW_START).describe_secret(SecretId=SECRET)
    return {
        "data_api": boto3.client("rds-data", config=SLOW_START),
        "bedrock": boto3.client("bedrock-runtime", config=SLOW_START),
        "rerank": boto3.client("bedrock-agent-runtime", config=SLOW_START),
        "target": {"resourceArn": cluster, "secretArn": secret["ARN"], "database": DATABASE},
    }


def search_passages(
    question: str,
    *,
    year_from: int | None = None,
    year_to: int | None = None,
    topic: str | None = None,
    doc_type: str | None = None,
    country: str | None = None,
) -> list[dict]:
    """Return up to 10 relevant passages, best first; an empty list means the corpus has no answer.

    Embeds the question (Cohere Embed v4), runs one hybrid SQL statement over `chunks` (meaning
    and keyword rankings fused by reciprocal rank fusion, filters applied in the same
    statement, chunks with a role such as references skipped, at most 6 chunks per document),
    reranks the top 25 with Amazon Rerank 1.0 and keeps the best 10 scoring at least
    MIN_RELEVANCE. Never padded.
    With no year filter given, a question that names its publication years ("published in
    2025") is filtered to them (publication_years).
    Each result has the citation fields plus `score` (the rerank relevance) and `neighbours`:
    the previous and next chunk of the same section, for the answering model to read around it.
    """
    if year_from is None and year_to is None:
        year_from, year_to, keywords = publication_years(question)
    else:
        keywords = question
    aws = _aws()
    params = {
        "q": keywords,
        "vec": json.dumps(_embed_query(aws["bedrock"], question)),
        "year_from": year_from,
        "year_to": year_to,
        "topic": topic,
        "doc_type": doc_type,
        "country": country,
    }
    candidates = _query_hybrid(aws["data_api"], aws["target"], params)
    results = _rerank(aws["rerank"], question, candidates)
    _attach_neighbours(aws["data_api"], aws["target"], results)
    return results


def publication_years(question: str) -> tuple[int | None, int | None, str]:
    """The publication years a question asks for, and the question without that phrase.

    "What did WRI publish in 2024 about heat?" gives (2024, 2024, "What did WRI about heat?"):
    the years become a filter, and the phrase leaves the keyword search, where "published"
    and "2024" would match most documents. The embedding and the reranker keep the whole
    question: without the phrase, every 2025 candidate for an ocean energy question fell
    below MIN_RELEVANCE. A question without the phrase gives (None, None)
    and the question unchanged.
    """
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


def _embed_query(bedrock, question: str) -> list[float]:
    body = {
        "texts": [question],
        "input_type": "search_query",
        "embedding_types": ["float"],
        "output_dimension": 1024,
    }
    response = bedrock.invoke_model(modelId=MODELS["embedder"], body=json.dumps(body))
    return json.loads(response["body"].read())["embeddings"]["float"][0]


def _query_hybrid(data_api, target: dict, params: dict) -> list[dict]:
    """Run the hybrid statement in a transaction so HNSW iterative scans can be switched on.

    Iterative scans keep the vector index scanning until a selective filter has its matches.
    """
    tx = data_api.begin_transaction(**target)["transactionId"]
    try:
        data_api.execute_statement(
            **target, transactionId=tx, sql="SET LOCAL hnsw.iterative_scan = relaxed_order"
        )
        rows = _rows(data_api, target, HYBRID_SQL, params, tx)
    except Exception:
        data_api.rollback_transaction(
            resourceArn=target["resourceArn"], secretArn=target["secretArn"], transactionId=tx
        )
        raise
    data_api.commit_transaction(
        resourceArn=target["resourceArn"], secretArn=target["secretArn"], transactionId=tx
    )
    return rows


def _rows(data_api, target: dict, sql: str, params: dict, tx: str | None = None) -> list[dict]:
    options = {"transactionId": tx} if tx else {}
    response = data_api.execute_statement(
        **target,
        sql=sql,
        parameters=[{"name": k, "value": _value(v)} for k, v in params.items()],
        formatRecordsAs="JSON",
        **options,
    )
    return json.loads(response["formattedRecords"])


def _value(value) -> dict:
    if value is None:
        return {"isNull": True}
    if isinstance(value, int):
        return {"longValue": value}
    return {"stringValue": value}


def _rerank(client, question: str, candidates: list[dict]) -> list[dict]:
    """Reorder candidates by Amazon Rerank 1.0 (see _rerank_text); keep the best RESULTS."""
    if not candidates:
        return []
    model_arn = f"arn:aws:bedrock:{client.meta.region_name}::foundation-model/{MODELS['reranker']}"
    response = client.rerank(
        queries=[{"type": "TEXT", "textQuery": {"text": question}}],
        sources=[
            {
                "type": "INLINE",
                "inlineDocumentSource": {
                    "type": "TEXT",
                    "textDocument": {"text": _rerank_text(row)},
                },
            }
            for row in candidates
        ],
        rerankingConfiguration={
            "type": "BEDROCK_RERANKING_MODEL",
            "bedrockRerankingConfiguration": {
                "modelConfiguration": {"modelArn": model_arn},
                "numberOfResults": min(RESULTS, len(candidates)),
            },
        },
    )
    return [
        _citation(candidates[hit["index"]]) | {"score": hit["relevanceScore"]}
        for hit in response["results"][:RESULTS]
        if hit["relevanceScore"] >= MIN_RELEVANCE
    ]


def _rerank_text(row: dict) -> str:
    """Title › section, then the description (else the content).

    Without the title, a passage that never names its subject ("the projects", "these
    sites") scores as unrelated: the offshore wind paper's passages never mention ocean energy.
    """
    address = " › ".join(part for part in (row["title"], row["section"]) if part)
    return f"{address}\n\n{row['description'] or row['content']}"


def _citation(row: dict) -> dict:
    return {key: row[key] for key in CITATION_KEYS}


def _attach_neighbours(data_api, target: dict, results: list[dict]) -> None:
    """Give every hit its previous and next chunk (same doc and section), in one statement.

    The answering model reads the passage in its context; the embedded chunks stay small,
    so each one still matches on one idea.
    """
    if not results:
        return
    params = {f"id{i}": hit["chunk_id"] for i, hit in enumerate(results)}
    ids = ", ".join(f":{name}" for name in params)
    rows = _rows(
        data_api,
        target,
        f"""SELECT h.chunk_id AS hit_id, {COLUMNS}
        FROM chunks h JOIN chunks c ON c.doc_id = h.doc_id AND c.seq IN (h.seq - 1, h.seq + 1)
          AND c.section IS NOT DISTINCT FROM h.section
        JOIN documents d ON d.doc_id = c.doc_id
        WHERE h.chunk_id IN ({ids}) ORDER BY c.seq""",
        params,
    )
    for hit in results:
        hit["neighbours"] = [_citation(r) for r in rows if r["hit_id"] == hit["chunk_id"]]


def _format(result: dict) -> str:
    pages = result["printed_page"]
    if result["printed_page_end"] != pages:
        pages += f"-{result['printed_page_end']}"
    where = f"{result['section']}, " if result["section"] else ""
    head = f"{result['title']} ({where}p. {pages}, {result['kind']}) {result['link']}"
    return f"[{result['score']:.3f}] {head}\n    {result['content'][:300]}"


def main() -> int:
    """Run one real search against the deployed index and print the results with citations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--topic")
    parser.add_argument("--year-from", type=int)
    parser.add_argument("--year-to", type=int)
    parser.add_argument("--doc-type")
    parser.add_argument("--country")
    args = parser.parse_args()
    results = search_passages(
        args.question,
        year_from=args.year_from,
        year_to=args.year_to,
        topic=args.topic,
        doc_type=args.doc_type,
        country=args.country,
    )
    if not results:
        print("No passages found.")
    for result in results:
        print(_format(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
