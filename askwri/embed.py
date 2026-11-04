"""Passage and query embeddings from the Bedrock embedding model named by ASKWRI_EMBEDDING_MODEL."""

import json
import os
from concurrent.futures import ThreadPoolExecutor

import boto3

DIMENSIONS = 1024  # must equal vector(1024) in db/schema.sql


def embed(texts: list[str], client=None, workers: int = 8) -> list[list[float]]:
    """Return one normalized embedding per text, in order.

    Calls bedrock-runtime InvokeModel once per text (Titan Text Embeddings V2 takes one text a
    call), `workers` at a time. Throttled calls are retried by botocore's standard retry mode.
    """
    client = client or boto3.client("bedrock-runtime")
    model_id = os.environ["ASKWRI_EMBEDDING_MODEL"]

    def one(text: str) -> list[float]:
        body = json.dumps({"inputText": text, "dimensions": DIMENSIONS, "normalize": True})
        response = client.invoke_model(modelId=model_id, body=body)
        return json.loads(response["body"].read())["embedding"]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, texts))
