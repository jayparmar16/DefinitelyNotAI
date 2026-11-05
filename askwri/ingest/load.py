"""Load the corpus into Aurora: sort, ingest, embed with Cohere v4, replace each document's rows.

Usage: `uv run python -m askwri.ingest.load [--reload] <year folder>...`, for example
`2024 2025 2026` (scripts/run-pipeline.sh wraps it). An undated document takes its folder's year.
Needs CORPUS_BUCKET and AWS credentials; writes through the RDS Data API, so no VPC access.
"""

import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from functools import cache
from pathlib import Path

import boto3
from botocore.config import Config

from askwri.ingest.chunks import Chunk
from askwri.ingest.document import IngestResult, ingest_document
from askwri.ingest.labels import catalog_row, document_card
from askwri.ingest.sort import KeptDocument, sort_corpus
from askwri.ingest.wri_site import WriSite
from askwri.models import MODELS, ModelError, cached_client, claude_client

CLUSTER = "askwri-db"
SECRET = "askwri/db"
# ASKWRI_DATABASE picks another database in the cluster, e.g. for an experiment beside the demo.
DATABASE = os.environ.get("ASKWRI_DATABASE", "askwri")
EMBED_BATCH = 96  # Cohere Embed v4 takes at most 96 texts per request
ROW_BATCH = 40  # chunk rows per Data API call: each carries a 1,024-float vector as text
# Parallel documents: PyMuPDF isn't thread-safe, so these are processes. Most time is spent
# waiting on Bedrock, so more workers than cores is fine; 8 stays well inside Bedrock quotas.
WORKERS = 8
# Cohere Embed v4 allows 300,000 tokens a minute, about a third of what the corpus needs: the
# embed calls of 8 workers get throttled, and adaptive retries wait instead of failing the run.
EMBED_RETRIES = Config(retries={"mode": "adaptive", "max_attempts": 10})

# Local record of the model's work, git-ignored: every Haiku reply (replayed by later loads,
# so a reload pays only for calls it has never made) and each loaded document's labels.
CACHE = Path(__file__).resolve().parents[2] / ".cache" / "ingest"

ARRAY_COLUMNS = (
    "authors", "tags", "countries", "replaces", "initiatives", "programs", "topics", "concepts",
    "keywords", "acronyms", "regions", "key_findings",
)  # fmt: skip
DOCUMENT_COLUMNS = [
    "doc_id", "file_sha256", "pdf_key", "title", "label_source", "url", "doi", "topic",
    "topic_source", "wri_type", "doc_type", "pub_date", "year", "date_source", "authors", "tags",
    "countries", "summary", "deadline", "language", "replaces", "abstract", "initiatives",
    "programs", "topics", "concepts", "keywords", "acronyms", "regions", "key_findings", "genre",
    "coverage_start", "coverage_end", "doc_tsv", "card_embedding",
]  # fmt: skip
CHUNK_COLUMNS = [
    "chunk_id", "doc_id", "seq", "kind", "pdf_page", "pdf_page_end", "printed_page",
    "printed_page_end", "printed_page_fallback", "section", "content", "description", "number",
    "quotable", "role", "embedding",
]  # fmt: skip
CASTS = {
    "pub_date": "CAST(:pub_date AS date)",
    "deadline": "CAST(:deadline AS date)",
    "embedding": "CAST(:embedding AS vector)",
    "card_embedding": "CAST(:card_embedding AS vector)",
    "doc_tsv": "to_tsvector('english', CAST(:doc_tsv AS text))",
} | {
    # The Data API has no array parameters for PostgreSQL: arrays travel as JSON text.
    name: f"ARRAY(SELECT json_array_elements_text(CAST(:{name} AS json)))"
    for name in ARRAY_COLUMNS
}


def document_row(
    kept: KeptDocument, result: IngestResult, file_sha256: str, card_embedding: list[float]
) -> dict:
    """The documents row: the wri.org or model labels, the sorter's fields and the card.

    `doc_tsv` is the keyword index of the document card plus the acronyms the text defines;
    `card_embedding` is the card's embedding.
    """
    labels = result.labels
    return {
        "doc_id": result.doc_id,
        "file_sha256": file_sha256,
        "pdf_key": pdf_key(result.doc_id),
        "title": labels.title,
        "label_source": labels.label_source,
        "url": labels.link,
        "doi": labels.doi,
        "topic": labels.topic,
        "topic_source": labels.topic_source,
        "wri_type": labels.wri_type,
        "doc_type": kept.doc_type,
        "pub_date": labels.published,
        "year": labels.year,
        "date_source": labels.date_source,
        "authors": list(labels.authors),
        "tags": list(labels.tags),
        "countries": list(labels.countries),
        "summary": labels.summary,
        "deadline": labels.deadline,
        "language": kept.language,
        "replaces": [path.name for path in kept.replaces],
        "abstract": labels.abstract,
        "initiatives": list(labels.initiatives),
        "programs": list(labels.programs),
        "topics": list(labels.topics),
        "concepts": list(labels.concepts),
        "keywords": list(labels.keywords),
        "acronyms": list(labels.acronyms),
        "regions": list(labels.regions),
        "key_findings": list(labels.key_findings),
        "genre": labels.genre,
        "coverage_start": labels.coverage_start,
        "coverage_end": labels.coverage_end,
        "doc_tsv": "\n".join([document_card(labels), *labels.acronyms]),
        "card_embedding": json.dumps(card_embedding),
    }


def chunk_row(chunk: Chunk, embedding: list[float]) -> dict:
    """One chunks row; the embedding goes in as pgvector's text form."""
    return {
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "seq": chunk.seq,
        "kind": chunk.kind,
        "pdf_page": chunk.pdf_page,
        "pdf_page_end": chunk.pdf_page_end,
        "printed_page": chunk.printed_page,
        "printed_page_end": chunk.printed_page_end,
        "printed_page_fallback": chunk.printed_page_fallback,
        "section": chunk.section,
        "content": chunk.text,
        "description": chunk.description or None,
        "number": chunk.number,
        "quotable": chunk.quotable,
        "role": chunk.role,
        "embedding": json.dumps(embedding),
    }


def pdf_key(doc_id: str) -> str:
    """Where the stored PDF lives in the corpus bucket: the citation fallback."""
    return f"raw/{doc_id}.pdf"


def replace_document(data_api, target: dict, doc_row: dict, chunk_rows: list[dict]) -> None:
    """Delete the document's rows and insert the new ones in one transaction.

    `target` holds resourceArn, secretArn and database. Deleting the documents row removes
    its old chunks too (ON DELETE CASCADE), so chunks the document no longer has disappear.
    """
    tx = data_api.begin_transaction(**target)["transactionId"]
    try:
        data_api.execute_statement(
            **target,
            transactionId=tx,
            sql="DELETE FROM documents WHERE doc_id = :doc_id",
            parameters=_parameters({"doc_id": doc_row["doc_id"]}),
        )
        data_api.execute_statement(
            **target,
            transactionId=tx,
            sql=_insert("documents", DOCUMENT_COLUMNS),
            parameters=_parameters(doc_row),
        )
        for start in range(0, len(chunk_rows), ROW_BATCH):
            data_api.batch_execute_statement(
                **target,
                transactionId=tx,
                sql=_insert("chunks", CHUNK_COLUMNS),
                parameterSets=[_parameters(row) for row in chunk_rows[start : start + ROW_BATCH]],
            )
    except Exception:
        data_api.rollback_transaction(resourceArn=target["resourceArn"],
                                      secretArn=target["secretArn"], transactionId=tx)  # fmt: skip
        raise
    data_api.commit_transaction(
        resourceArn=target["resourceArn"], secretArn=target["secretArn"], transactionId=tx
    )


def embed(bedrock, texts: list[str]) -> list[list[float]]:
    """Cohere Embed v4 document embeddings, 1,024 dimensions, in batches of EMBED_BATCH."""
    vectors = []
    for start in range(0, len(texts), EMBED_BATCH):
        body = {
            "texts": texts[start : start + EMBED_BATCH],
            "input_type": "search_document",
            "embedding_types": ["float"],
            "output_dimension": 1024,
        }
        response = bedrock.invoke_model(modelId=MODELS["embedder"], body=json.dumps(body))
        vectors += json.loads(response["body"].read())["embeddings"]["float"]
    return vectors


def _insert(table: str, columns: list[str]) -> str:
    values = ", ".join(CASTS.get(name, f":{name}") for name in columns)
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({values})"


def _parameters(row: dict) -> list[dict]:
    return [{"name": name, "value": _value(value)} for name, value in row.items()]


def _value(value) -> dict:
    if value is None:
        return {"isNull": True}
    if isinstance(value, bool):  # before int: bool is an int subclass
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"longValue": value}
    if isinstance(value, list):
        return {"stringValue": json.dumps(value)}
    return {"stringValue": value}


@cache
def _aws() -> dict:
    """Per-process clients and the Data API target (boto3 clients aren't shared across processes)."""
    rds_arn = boto3.client("rds").describe_db_clusters(DBClusterIdentifier=CLUSTER)
    return {
        "data_api": boto3.client("rds-data"),
        "bedrock": boto3.client("bedrock-runtime", config=EMBED_RETRIES),
        "s3": boto3.client("s3"),
        "target": {
            "resourceArn": rds_arn["DBClusters"][0]["DBClusterArn"],
            "secretArn": boto3.client("secretsmanager").describe_secret(SecretId=SECRET)["ARN"],
            "database": DATABASE,
        },
        "site": WriSite(),
        "claude": cached_client(claude_client(), CACHE / "model-calls"),
    }


def _loaded_hashes() -> dict[str, str]:
    """File hashes of the documents loaded with a card; rows from before the card load again.

    So a plain rerun after an interrupted reload picks up only the documents it had not reached.
    """
    aws = _aws()
    result = aws["data_api"].execute_statement(
        **aws["target"],
        sql="SELECT doc_id, file_sha256 FROM documents WHERE card_embedding IS NOT NULL",
    )
    return {row[0]["stringValue"]: row[1]["stringValue"] for row in result["records"]}


def _save_labels(result: IngestResult) -> None:
    """Write CACHE/documents/<database>/<doc_id>.json: the catalog row and table descriptions."""
    row = catalog_row(result.doc_id, result.pdf_file, result.labels) | {
        "table_descriptions": {c.chunk_id: c.description for c in result.chunks if c.description}
    }
    path = CACHE / "documents" / DATABASE / f"{result.doc_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_one(job: tuple[KeptDocument, str]) -> str:
    """Ingest, upload, embed and write one document; returns its report line."""
    kept, file_sha256 = job
    aws = _aws()
    try:
        result = ingest_document(kept.path, aws["site"], aws["claude"])
    except ModelError as error:
        return f"SKIPPED {kept.doc_id}: model error: {error}"
    except ValueError as error:  # an off-list label: this document only, not the whole run
        return f"SKIPPED {kept.doc_id}: bad label: {error}"
    if not result.audit.passed:
        return f"SKIPPED {kept.doc_id}: audit failed: {result.audit.failures[0]}"
    _save_labels(result)
    aws["s3"].upload_file(str(kept.path), os.environ["CORPUS_BUCKET"], pdf_key(result.doc_id))
    texts = [document_card(result.labels), *(chunk.indexed_text for chunk in result.chunks)]
    card_vector, *vectors = embed(aws["bedrock"], texts)
    rows = [chunk_row(chunk, vector) for chunk, vector in zip(result.chunks, vectors, strict=True)]
    doc_row = document_row(kept, result, file_sha256, card_vector)
    replace_document(aws["data_api"], aws["target"], doc_row, rows)
    labels = result.labels
    return (
        f"LOADED {result.doc_id}: {len(rows)} chunks, labels {labels.label_source}, "
        f"year {labels.year} ({labels.date_source}), topics {', '.join(labels.topics) or '-'}"
    )


def main() -> int:
    """Load every kept PDF under the given folders; loaded, unchanged PDFs are skipped.

    A document loaded before the richer labels (no card) counts as not loaded. `--reload`
    loads every document again, so a change to ingestion reaches all of them.
    Returns 1 if any document was skipped (model error, bad label or failed audit), else 0.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", nargs="+", type=Path, help="corpus folders, e.g. 2024 2025 2026")
    parser.add_argument(
        "--reload", action="store_true", help="also reload PDFs already loaded and unchanged"
    )
    args = parser.parse_args()
    pdfs = sorted(pdf for folder in args.folders for pdf in folder.glob("*.pdf"))
    corpus = sort_corpus(pdfs)
    print(f"{len(corpus.kept)} kept, {len(corpus.dropped)} dropped by sorting", flush=True)
    loaded = {} if args.reload else _loaded_hashes()
    jobs = []
    for kept in corpus.kept:
        file_sha256 = hashlib.sha256(kept.path.read_bytes()).hexdigest()
        if loaded.get(kept.doc_id) != file_sha256:
            jobs.append((kept, file_sha256))
    print(f"{len(corpus.kept) - len(jobs)} already loaded, {len(jobs)} to load", flush=True)
    skipped = 0
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        for line in pool.map(_load_one, jobs):
            skipped += line.startswith("SKIPPED")
            print(line, flush=True)
    print(f"done: {len(jobs) - skipped} loaded, {skipped} skipped")
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
