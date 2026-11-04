"""Hybrid passage search over Aurora: meaning + keyword search, fused, reranked, with neighbours.

Usage: `uv run python -m askwri.search "question" [--topic X] [--year-from N]`.
Needs AWS credentials in the environment; reads through the RDS Data API (no VPC access).
"""

import argparse
import json
import sys
from functools import cache

import boto3
from botocore.config import Config

from askwri.models import MODELS

CLUSTER = "askwri-db"
SECRET = "askwri/db"
DATABASE = "askwri"
CANDIDATES = 25  # per ranking, and after fusion: what the reranker sees
RESULTS = 6
# Rerank relevance below this is not an answer: on live queries relevant hits scored 0.08-0.99
# and off-topic ones about 0.000. A starting point for #26 to tune on the evaluation set.
MIN_RELEVANCE = 0.05
SHORT_CHUNK_CHARS = 400  # shorter hits come back with their neighbours
RRF_K = 60  # reciprocal rank fusion constant
# The first query after an Aurora auto-pause can take 30 s or more.
SLOW_START = Config(connect_timeout=90, read_timeout=90, retries={"max_attempts": 3})

COLUMNS = """c.chunk_id, c.doc_id, d.title, coalesce(d.url, d.pdf_key) AS link,
  c.pdf_page, c.pdf_page_end, c.printed_page, c.printed_page_end, c.section, c.kind,
  c.quotable, c.content, c.description, c.number, c.figure_key"""
FILTERS = """(CAST(:year_from AS int) IS NULL OR d.year >= CAST(:year_from AS int))
  AND (CAST(:year_to AS int) IS NULL OR d.year <= CAST(:year_to AS int))
  AND (CAST(:topic AS text) IS NULL OR d.topic = CAST(:topic AS text))
  AND (CAST(:doc_type AS text) IS NULL OR d.doc_type = CAST(:doc_type AS text))
  AND (CAST(:country AS text) IS NULL OR CAST(:country AS text) = ANY(d.countries))"""
RANK = "ts_rank(c.tsv, websearch_to_tsquery('english', :q))"
HYBRID_SQL = f"""
WITH meaning AS (
  SELECT c.chunk_id, row_number() OVER (ORDER BY c.embedding <=> CAST(:vec AS vector)) AS r
  FROM chunks c JOIN documents d USING (doc_id)
  WHERE {FILTERS}
  ORDER BY c.embedding <=> CAST(:vec AS vector) LIMIT {CANDIDATES}),
keyword AS (
  SELECT c.chunk_id, row_number() OVER (ORDER BY {RANK} DESC) AS r
  FROM chunks c JOIN documents d USING (doc_id)
  WHERE c.tsv @@ websearch_to_tsquery('english', :q) AND {FILTERS}
  ORDER BY {RANK} DESC LIMIT {CANDIDATES})
SELECT {COLUMNS}, sum(1.0 / ({RRF_K} + x.r)) AS fused
FROM (SELECT * FROM meaning UNION ALL SELECT * FROM keyword) x
JOIN chunks c USING (chunk_id) JOIN documents d USING (doc_id)
GROUP BY c.chunk_id, d.doc_id, d.title, d.url, d.pdf_key
ORDER BY fused DESC LIMIT {CANDIDATES}
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
    """Return up to 6 relevant passages, best first; an empty list means the corpus has no answer.

    Embeds the question (Cohere Embed v4), runs one hybrid SQL statement over `chunks` (meaning
    and keyword rankings fused by reciprocal rank fusion, filters applied in the same
    statement), reranks the top 25 with Amazon Rerank 1.0 and keeps the best 6 scoring at least MIN_RELEVANCE.
    Never padded.
    Each result has the citation fields plus `score` (the rerank relevance). A hit shorter than
    400 characters also has `neighbours`: the previous and next chunk of the same section.
    """
    aws = _aws()
    params = {
        "q": question,
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
    """Reorder candidates by Amazon Rerank 1.0 on description (else content); keep the best 6."""
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
                    "textDocument": {"text": row["description"] or row["content"]},
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


def _citation(row: dict) -> dict:
    return {key: row[key] for key in CITATION_KEYS}


def _attach_neighbours(data_api, target: dict, results: list[dict]) -> None:
    """Give each short hit its previous and next chunk (same doc and section), in one statement."""
    short = [result for result in results if len(result["content"]) < SHORT_CHUNK_CHARS]
    if not short:
        return
    params = {f"id{i}": hit["chunk_id"] for i, hit in enumerate(short)}
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
    for hit in short:
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
