"""Apply db/schema.sql to askwri-db through the RDS Data API (no VPC access needed).

Runs anywhere with the team account's credentials, including CloudShell:
`python3 db/apply_schema.py`. Uses only the standard library and boto3.
"""

import os
import re
import sys
from pathlib import Path

import boto3

CLUSTER = "askwri-db"
SECRET = "askwri/db"
# ASKWRI_DATABASE picks another database in the cluster, e.g. for an experiment beside the demo.
DATABASE = os.environ.get("ASKWRI_DATABASE", "askwri")


def split_statements(sql: str) -> list[str]:
    """Split SQL into statements at ";" ending a line; "--" comment lines are dropped.

    Semicolons inside a line (as in a one-line DO block) don't split.
    """
    lines = [line for line in sql.splitlines() if not line.lstrip().startswith("--")]
    parts = re.split(r";[ \t]*(?:--[^\n]*)?$", "\n".join(lines), flags=re.MULTILINE)
    return [part.strip() for part in parts if part.strip()]


def main() -> int:
    """Run every statement in order; the first failure stops the run with its error."""
    cluster_arn = boto3.client("rds").describe_db_clusters(DBClusterIdentifier=CLUSTER)[
        "DBClusters"
    ][0]["DBClusterArn"]
    secret_arn = boto3.client("secretsmanager").describe_secret(SecretId=SECRET)["ARN"]
    data_api = boto3.client("rds-data")
    statements = split_statements((Path(__file__).parent / "schema.sql").read_text())
    for statement in statements:
        print(statement.splitlines()[0])
        data_api.execute_statement(
            resourceArn=cluster_arn, secretArn=secret_arn, database=DATABASE, sql=statement
        )
    print(f"Applied {len(statements)} statements to {CLUSTER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
