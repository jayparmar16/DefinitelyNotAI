"""Load the corpus into Aurora: sort, ingest, embed with Cohere v4, replace each document's rows.

Usage: `uv run python -m askwri.ingest.load <pdf folder>...` (scripts/run-pipeline.sh wraps it).
Needs CORPUS_BUCKET and AWS credentials; writes through the RDS Data API, so no VPC access.
"""

import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from functools import cache
from pathlib import Path

import boto3

from askwri.ingest.chunks import Chunk
from askwri.ingest.document import IngestResult, ingest_document
from askwri.ingest.sort import KeptDocument, sort_corpus
from askwri.ingest.wri_site import WriSite
from askwri.models import MODELS, ModelError, claude_client

CLUSTER = "askwri-db"
SECRET = "askwri/db"
DATABASE = "askwri"
EMBED_BATCH = 96  # Cohere Embed v4 takes at most 96 texts per request
ROW_BATCH = 40  # chunk rows per Data API call: each carries a 1,024-float vector as text
# Parallel documents: PyMuPDF isn't thread-safe, so these are processes. Most time is spent
# waiting on Bedrock, so more workers than cores is fine; 8 stays well inside Bedrock quotas.
WORKERS = 8

DOCUMENT_COLUMNS = [
    "doc_id", "file_sha256", "pdf_key", "title", "label_source", "url", "doi", "topic",
    "topic_source", "wri_type", "doc_type", "pub_date", "year", "authors", "tags", "countries",
    "summary", "deadline", "language", "replaces",
]  # fmt: skip
CHUNK_COLUMNS = [
    "chunk_id", "doc_id", "seq", "kind", "pdf_page", "pdf_page_end", "printed_page",
    "printed_page_end", "printed_page_fallback", "section", "content", "description", "number",
    "figure_key", "quotable", "embedding",
]  # fmt: skip
CASTS = {
    "pub_date": "CAST(:pub_date AS date)",
    "deadline": "CAST(:deadline AS date)",
    "embedding": "CAST(:embedding AS vector)",
} | {
    # The Data API has no array parameters for PostgreSQL: arrays travel as JSON text.
    name: f"ARRAY(SELECT json_array_elements_text(CAST(:{name} AS json)))"
    for name in ("authors", "tags", "countries", "replaces")
}


def document_row(kept: KeptDocument, result: IngestResult, file_sha256: str) -> dict:
    """The documents row: the wri.org or model labels plus the sorter's fields."""
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
        "year": int(labels.published[:4]) if labels.published else None,
        "authors": list(labels.authors),
        "tags": list(labels.tags),
        "countries": list(labels.countries),
        "summary": labels.summary,
        "deadline": labels.deadline,
        "language": kept.language,
        "replaces": [path.name for path in kept.replaces],
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
        "figure_key": figure_key(chunk.chunk_id) if chunk.figure else None,
        "quotable": chunk.quotable,
        "embedding": json.dumps(embedding),
    }


def pdf_key(doc_id: str) -> str:
    """Where the stored PDF lives in the corpus bucket: the citation fallback."""
    return f"raw/{doc_id}.pdf"


def figure_key(chunk_id: str) -> str:
    """Where a picture chunk's PNG lives in the corpus bucket, e.g. "figures/doc-p3-1.png"."""
    return f"figures/{chunk_id.replace('#', '-')}.png"


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
        "bedrock": boto3.client("bedrock-runtime"),
        "s3": boto3.client("s3"),
        "target": {
            "resourceArn": rds_arn["DBClusters"][0]["DBClusterArn"],
            "secretArn": boto3.client("secretsmanager").describe_secret(SecretId=SECRET)["ARN"],
            "database": DATABASE,
        },
        "site": WriSite(),
        "claude": claude_client(),
    }


def _loaded_hashes() -> dict[str, str]:
    aws = _aws()
    result = aws["data_api"].execute_statement(
        **aws["target"], sql="SELECT doc_id, file_sha256 FROM documents"
    )
    return {row[0]["stringValue"]: row[1]["stringValue"] for row in result["records"]}


def _load_one(job: tuple[KeptDocument, str]) -> str:
    """Ingest, upload, embed and write one document; returns its report line."""
    kept, file_sha256 = job
    aws = _aws()
    try:
        result = ingest_document(kept.path, aws["site"], aws["claude"])
    except ModelError as error:
        return f"SKIPPED {kept.doc_id}: model error: {error}"
    if not result.audit.passed:
        return f"SKIPPED {kept.doc_id}: audit failed: {result.audit.failures[0]}"
    aws["s3"].upload_file(str(kept.path), os.environ["CORPUS_BUCKET"], pdf_key(result.doc_id))
    for chunk in result.chunks:
        if chunk.figure:
            aws["s3"].put_object(
                Bucket=os.environ["CORPUS_BUCKET"],
                Key=figure_key(chunk.chunk_id),
                Body=chunk.figure.png,
                ContentType="image/png",
            )
    vectors = embed(aws["bedrock"], [chunk.indexed_text for chunk in result.chunks])
    rows = [chunk_row(chunk, vector) for chunk, vector in zip(result.chunks, vectors, strict=True)]
    replace_document(aws["data_api"], aws["target"], document_row(kept, result, file_sha256), rows)
    return (
        f"LOADED {result.doc_id}: {len(rows)} chunks, labels {result.labels.label_source}, "
        f"{result.pictures.summary}"
    )


def main() -> int:
    """Load every kept PDF under the given folders; already-loaded, unchanged PDFs are skipped.

    Returns 1 if any document was skipped (model error or failed audit), else 0.
    """
    pdfs = sorted(pdf for folder in sys.argv[1:] for pdf in Path(folder).glob("*.pdf"))
    corpus = sort_corpus(pdfs)
    print(f"{len(corpus.kept)} kept, {len(corpus.dropped)} dropped by sorting", flush=True)
    loaded = _loaded_hashes()
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
