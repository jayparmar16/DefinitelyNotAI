"""Run one SQL statement on askwri-db through the RDS Data API, signed with the credentials in .env.

Usage: `uv run python db/query.py "SELECT count(*) FROM documents"`. See docs/query-aurora.md.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

CLUSTER = "askwri-db"
SECRET = "askwri/db"
# ASKWRI_DATABASE picks another database in the cluster, e.g. for an experiment beside the demo.
DATABASE = os.environ.get("ASKWRI_DATABASE", "askwri")
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
# A paused Serverless v2 cluster refuses requests until it resumes (15 s or more).
RESUME_ATTEMPTS = 7
RESUME_WAIT_SECONDS = 10


def read_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines; skips blanks and # comments, drops `export` and quotes."""
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        values[key.strip()] = value.strip().strip("\"'")
    return values


def session_from_env(env: dict[str, str]) -> boto3.Session:
    """A boto3 session with the region and temporary credentials from .env.

    These take precedence over AWS_* environment variables and AWS_PROFILE.
    """
    return boto3.Session(
        region_name=env["AWS_DEFAULT_REGION"],
        aws_access_key_id=env["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=env["AWS_SECRET_ACCESS_KEY"],
        aws_session_token=env["AWS_SESSION_TOKEN"],
    )


def run_sql(session: boto3.Session, sql: str) -> dict:
    """Run sql on askwri-db as the master user (askwri/db secret); rows come back as JSON.

    Waits and retries while a paused cluster resumes.
    """
    cluster_arn = session.client("rds").describe_db_clusters(DBClusterIdentifier=CLUSTER)[
        "DBClusters"
    ][0]["DBClusterArn"]
    secret_arn = session.client("secretsmanager").describe_secret(SecretId=SECRET)["ARN"]
    data_api = session.client("rds-data")
    request = {
        "resourceArn": cluster_arn,
        "secretArn": secret_arn,
        "database": DATABASE,
        "sql": sql,
        "formatRecordsAs": "JSON",
    }
    for _ in range(RESUME_ATTEMPTS - 1):
        try:
            return data_api.execute_statement(**request)
        except data_api.exceptions.DatabaseResumingException:
            print(f"{CLUSTER} is resuming, retrying in {RESUME_WAIT_SECONDS} s", file=sys.stderr)
            time.sleep(RESUME_WAIT_SECONDS)
    return data_api.execute_statement(**request)


def main() -> int:
    """Print the statement's rows as JSON, or the number of rows it changed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sql", nargs="?", default="SELECT version()")
    args = parser.parse_args()

    session = session_from_env(read_env_file(ENV_FILE))
    try:
        response = run_sql(session, args.sql)
    except ClientError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if "formattedRecords" in response:
        print(json.dumps(json.loads(response["formattedRecords"]), indent=2))
    else:
        print(f"{response['numberOfRecordsUpdated']} rows changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
