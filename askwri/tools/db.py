"""Connections to askwri-db from inside the VPC, signed in with IAM database authentication."""

import os

import boto3
import psycopg
from psycopg.rows import dict_row


def connect() -> psycopg.Connection:
    """Open a connection as DB_USER with a 15-minute IAM token; rows come back as dicts.

    Reads DB_HOST, DB_NAME and DB_USER. The first query after Aurora auto-pauses waits while
    the cluster resumes (15 s or more), so callers need timeouts above that.
    """
    host, user = os.environ["DB_HOST"], os.environ["DB_USER"]
    token = boto3.client("rds").generate_db_auth_token(host, 5432, user)
    connection = psycopg.connect(
        host=host,
        dbname=os.environ["DB_NAME"],
        user=user,
        password=token,
        sslmode="require",
        connect_timeout=60,
        row_factory=dict_row,
    )
    # Filtered vector search keeps scanning the HNSW index until enough rows pass the filter.
    connection.execute("SET hnsw.iterative_scan = relaxed_order")
    return connection
