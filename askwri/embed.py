"""Query embeddings from the Bedrock model named by ASKWRI_EMBEDDING_MODEL (Cohere Embed v4).

Passages are embedded by the ingestion pipeline (askwri.ingest.load) as "search_document";
questions are embedded here as "search_query", the pairing Cohere's retrieval expects.
"""

import json
import os

import boto3

DIMENSIONS = 1024  # must equal vector(1024) in db/schema.sql
BATCH = 96  # Cohere Embed v4 takes at most 96 texts per request


def embed(texts: list[str], client=None) -> list[list[float]]:
    """Return one embedding per query text, in order (one InvokeModel call per 96 texts)."""
    client = client or boto3.client("bedrock-runtime")
    model_id = os.environ["ASKWRI_EMBEDDING_MODEL"]
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH):
        body = json.dumps(
            {
                "texts": texts[start : start + BATCH],
                "input_type": "search_query",
                "embedding_types": ["float"],
                "output_dimension": DIMENSIONS,
            }
        )
        response = client.invoke_model(modelId=model_id, body=body)
        vectors += json.loads(response["body"].read())["embeddings"]["float"]
    return vectors
