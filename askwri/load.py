"""Load the ingestion pipeline's output (chunk files, sidecars, catalog.json) into askwri-db.

`python -m askwri.load <ingest out dir> --pdfs <dir of the source PDFs>` stores each PDF in the
corpus bucket under raw/, embeds every chunk and writes documents and chunks through the RDS
Data API, so it runs from a laptop without VPC access. Rerunning replaces a document's chunks.
"""

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import boto3

from askwri.embed import embed

CLUSTER = "askwri-db"
SECRET = "askwri/db"
DATABASE = "askwri"
BATCH = 25  # chunk rows per Data API call; each carries a 1024-float vector

DOCUMENT_SQL = """
INSERT INTO documents (doc_id, title, url, doi, file_sha256, pdf_key, year, pub_date,
  date_source, date_confidence, pub_type, topic, topic_source, label_source, tags, countries,
  authors, summary)
VALUES (:doc_id, :title, :url, :doi, :file_sha256, :pdf_key, :year, CAST(:pub_date AS date),
  :date_source, :date_confidence, :pub_type, :topic, :topic_source, :label_source,
  ARRAY(SELECT jsonb_array_elements_text(CAST(:tags AS jsonb))),
  ARRAY(SELECT jsonb_array_elements_text(CAST(:countries AS jsonb))),
  ARRAY(SELECT jsonb_array_elements_text(CAST(:authors AS jsonb))), :summary)
ON CONFLICT (doc_id) DO UPDATE SET title = EXCLUDED.title, url = EXCLUDED.url,
  doi = EXCLUDED.doi, file_sha256 = EXCLUDED.file_sha256, pdf_key = EXCLUDED.pdf_key,
  year = EXCLUDED.year, pub_date = EXCLUDED.pub_date, date_source = EXCLUDED.date_source,
  date_confidence = EXCLUDED.date_confidence, pub_type = EXCLUDED.pub_type,
  topic = EXCLUDED.topic, topic_source = EXCLUDED.topic_source,
  label_source = EXCLUDED.label_source, tags = EXCLUDED.tags, countries = EXCLUDED.countries,
  authors = EXCLUDED.authors, summary = EXCLUDED.summary
"""

CHUNK_SQL = """
INSERT INTO chunks (chunk_id, doc_id, seq, page, page_end, printed_page, printed_page_end,
  printed_page_fallback, section, kind, quotable, address, content, embedding)
VALUES (:chunk_id, :doc_id, :seq, :page, :page_end, :printed_page, :printed_page_end,
  :printed_page_fallback, :section, :kind, :quotable, :address, :content,
  CAST(:embedding AS vector))
"""


@dataclass(frozen=True)
class ChunkRecord:
    """One chunk as the ingestion pipeline writes it: its sidecar attributes and file text."""

    attributes: dict
    indexed_text: str  # "<address>\n\n<passage>", the text that gets embedded


def document_row(catalog_row: dict, file_sha256: str) -> dict:
    """Map a catalog row to a documents row.

    Dates: wri.org's publication date is high confidence. Without one the document is stored
    undated; the printed-date and file-date rules belong to ingestion.
    """
    published = catalog_row.get("published")
    return {
        "doc_id": catalog_row["doc_id"],
        "title": catalog_row["title"],
        "url": catalog_row.get("link"),
        "doi": catalog_row.get("doi"),
        "file_sha256": file_sha256,
        "pdf_key": f"raw/{catalog_row['pdf_file']}",
        "year": int(published[:4]) if published else None,
        "pub_date": published,
        "date_source": "wri.org" if published else "none",
        "date_confidence": "high" if published else "undated",
        "pub_type": publication_type(catalog_row),
        "topic": catalog_row.get("topic"),
        "topic_source": catalog_row.get("topic_source"),
        "label_source": catalog_row["label_source"],
        "tags": json.dumps(catalog_row.get("tags") or [], ensure_ascii=False),
        "countries": json.dumps(catalog_row.get("countries") or [], ensure_ascii=False),
        "authors": json.dumps(catalog_row.get("authors") or [], ensure_ascii=False),
        "summary": catalog_row.get("summary"),
    }


# WRI DOIs name the publication type: 10.46830/wriwp.25.00035 is a working paper.
DOI_TYPES = {
    "wrirpt": "Report",
    "wriwp": "Working paper",
    "writn": "Technical note",
    "wriib": "Issue brief",
}


def publication_type(catalog_row: dict) -> str | None:
    """WRI's publication type, in the UI's wording: from the DOI's type code, else the sorter's
    doc_type, else wri.org's own type (which is only "Research" or "Data")."""
    code = re.match(r"10\.46830/([a-z]+)\.", catalog_row.get("doi") or "")
    if code and code.group(1) in DOI_TYPES:
        return DOI_TYPES[code.group(1)]
    doc_type = catalog_row.get("doc_type")
    if doc_type and doc_type != "other":
        return "Report" if doc_type == "research report" else doc_type.capitalize()
    return catalog_row.get("wri_type")


def chunk_row(record: ChunkRecord, embedding: list[float]) -> dict:
    """Map one chunk record to a chunks row; the passage is the file text after its address."""
    attributes = record.attributes
    address, separator, content = record.indexed_text.partition("\n\n")
    if not separator:  # a chunk is always "<address>\n\n<passage>"; anything else is a bug
        raise ValueError(f"{attributes['chunk_id']}: chunk text has no address line")
    return {
        "chunk_id": attributes["chunk_id"],
        "doc_id": attributes["doc_id"],
        "seq": attributes["seq"],
        "page": attributes["pdf_page"],
        "page_end": attributes["pdf_page_end"],
        "printed_page": attributes["printed_page"],
        "printed_page_end": attributes["printed_page_end"],
        "printed_page_fallback": attributes["printed_page_fallback"],
        "section": attributes.get("section", ""),
        "kind": attributes["kind"],
        "quotable": attributes["quotable"],
        "address": address,
        "content": content,
        "embedding": json.dumps(embedding),
    }


def data_api_parameters(row: dict) -> list[dict]:
    """Encode a row as RDS Data API parameters: None is SQL NULL, bools and ints keep type."""

    def value(item):
        if item is None:
            return {"isNull": True}
        if isinstance(item, bool):  # before int: bool is a subclass of int
            return {"booleanValue": item}
        if isinstance(item, int):
            return {"longValue": item}
        return {"stringValue": str(item)}

    return [{"name": name, "value": value(item)} for name, item in row.items()]


def read_chunks(doc_dir: Path) -> list[ChunkRecord]:
    """Read every chunk file and its .metadata.json sidecar in a document folder, by seq."""
    records = []
    for sidecar in doc_dir.glob("*.txt.metadata.json"):
        attributes = json.loads(sidecar.read_text(encoding="utf-8"))["metadataAttributes"]
        text = sidecar.with_name(sidecar.name.removesuffix(".metadata.json")).read_text("utf-8")
        records.append(ChunkRecord(attributes=attributes, indexed_text=text))
    return sorted(records, key=lambda record: record.attributes["seq"])


def load_document(row: dict, records: list[ChunkRecord], data_api, arns: dict) -> None:
    """Write one document and all its chunks in one transaction, replacing any earlier load."""
    embeddings = embed([record.indexed_text for record in records])
    chunk_rows = [chunk_row(r, e) for r, e in zip(records, embeddings, strict=True)]
    transaction = data_api.begin_transaction(**arns)["transactionId"]
    try:
        data_api.execute_statement(
            **arns, transactionId=transaction, sql=DOCUMENT_SQL, parameters=data_api_parameters(row)
        )
        data_api.execute_statement(
            **arns,
            transactionId=transaction,
            sql="DELETE FROM chunks WHERE doc_id = :doc_id",
            parameters=data_api_parameters({"doc_id": row["doc_id"]}),
        )
        for start in range(0, len(chunk_rows), BATCH):
            data_api.batch_execute_statement(
                **arns,
                transactionId=transaction,
                sql=CHUNK_SQL,
                parameterSets=[data_api_parameters(r) for r in chunk_rows[start : start + BATCH]],
            )
    except Exception:
        data_api.rollback_transaction(
            resourceArn=arns["resourceArn"], secretArn=arns["secretArn"], transactionId=transaction
        )
        raise
    data_api.commit_transaction(
        resourceArn=arns["resourceArn"], secretArn=arns["secretArn"], transactionId=transaction
    )


def main() -> int:
    """Load every document in the catalog. Needs ASKWRI_EMBEDDING_MODEL and the team profile."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ingested", type=Path, help="folder written by python -m askwri.ingest")
    parser.add_argument("--pdfs", type=Path, required=True, help="folder with the source PDFs")
    args = parser.parse_args()

    account = boto3.client("sts").get_caller_identity()["Account"]
    bucket = f"askwri-corpus-{account}"
    arns = {
        "resourceArn": boto3.client("rds").describe_db_clusters(DBClusterIdentifier=CLUSTER)[
            "DBClusters"
        ][0]["DBClusterArn"],
        "secretArn": boto3.client("secretsmanager").describe_secret(SecretId=SECRET)["ARN"],
        "database": DATABASE,
    }
    s3, data_api = boto3.client("s3"), boto3.client("rds-data")

    catalog = json.loads((args.ingested / "catalog.json").read_text(encoding="utf-8"))
    for entry in catalog:
        pdf = args.pdfs / entry["pdf_file"]
        row = document_row(entry, hashlib.sha256(pdf.read_bytes()).hexdigest())
        s3.upload_file(
            str(pdf), bucket, row["pdf_key"], ExtraArgs={"ContentType": "application/pdf"}
        )
        records = read_chunks(args.ingested / entry["doc_id"])
        load_document(row, records, data_api, arns)
        print(f"{entry['doc_id']}: {len(records)} chunks loaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
