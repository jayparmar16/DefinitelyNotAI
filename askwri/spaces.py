"""Topic spaces for the UI: how many publications each of WRI's topics holds.

`uv run python -m askwri.spaces > web/public/spaces.json` (scripts/deploy-web.sh runs it before
each build), so the sidebar shows counts without a call per page load. Reads askwri-db through
the RDS Data API with the team account's credentials.
"""

import json
import sys
from datetime import UTC, datetime

import boto3

from askwri.ingest.load import CLUSTER, DATABASE, SECRET
from askwri.ingest.model_labels import TOPICS

# What a space can search: every topic a document covers (at most two; one for documents
# loaded before that), leaving out the types search skips unless asked (askwri/tools/search.py).
SEARCHABLE = "coalesce(d.pub_type, '') NOT IN ('RFP', 'Newsletter', 'Dataset documentation')"
COUNTS_SQL = f"""
SELECT t.topic, count(DISTINCT d.doc_id) AS documents
FROM documents_v d, unnest(coalesce(nullif(d.topics, '{{}}'), ARRAY[d.topic])) AS t(topic)
WHERE {SEARCHABLE}
GROUP BY t.topic
"""
TOTAL_SQL = f"SELECT count(*) AS n FROM documents_v d WHERE {SEARCHABLE}"


def spaces(counts: dict[str, int], total: int, now: datetime) -> dict:
    """The spaces file: every WRI topic in the pipeline's order, with its count (0 if none)."""
    return {
        "generatedAt": now.isoformat(timespec="seconds"),
        "total": total,
        "spaces": [{"name": topic, "documents": counts.get(topic, 0)} for topic in TOPICS],
    }


def _rows(data_api, cluster: str, secret: str, sql: str) -> list[dict]:
    reply = data_api.execute_statement(
        resourceArn=cluster, secretArn=secret, database=DATABASE, sql=sql, formatRecordsAs="JSON"
    )
    return json.loads(reply["formattedRecords"])


def main() -> int:
    """Print the spaces file for the documents now in askwri-db."""
    cluster = boto3.client("rds").describe_db_clusters(DBClusterIdentifier=CLUSTER)["DBClusters"][
        0
    ]["DBClusterArn"]
    secret = boto3.client("secretsmanager").describe_secret(SecretId=SECRET)["ARN"]
    data_api = boto3.client("rds-data")
    counts = {r["topic"]: r["documents"] for r in _rows(data_api, cluster, secret, COUNTS_SQL)}
    total = _rows(data_api, cluster, secret, TOTAL_SQL)[0]["n"]
    json.dump(spaces(counts, total, datetime.now(UTC)), sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
