# Query Aurora with credentials from `.env`

`db/query.py` runs one SQL statement on `askwri-db` and prints the rows as JSON.

## 1. Put your credentials in `.env`

In the repo root:

```sh
AWS_DEFAULT_REGION=us-west-2
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=...
```

Git ignores `.env`, so it is never committed. Session tokens expire: on `ExpiredToken`,
paste in fresh values.

## 2. Run a query

```sh
uv run python db/query.py                     # SELECT version()
uv run python db/query.py "SELECT doc_id, title FROM documents LIMIT 5"
uv run python db/query.py "SELECT count(*) FROM chunks"
```

## How it works

1. Reads the four values from `.env` and builds a boto3 session from them. They win over
   any `AWS_*` variables or `AWS_PROFILE` in your shell.
2. Looks up the cluster (`askwri-db`) and the secret (`askwri/db`) by name.
3. Sends the SQL to the **RDS Data API**, an HTTPS endpoint. The cluster is private, but
   the Data API needs no VPC access, open port or Postgres driver.
4. If the cluster has auto-paused, the script retries for about a minute while it resumes.

## Permissions your credentials need

- `rds:DescribeDBClusters`
- `secretsmanager:DescribeSecret` and `secretsmanager:GetSecretValue`
- `rds-data:ExecuteStatement`

## Careful

The script signs in as the master user (`askwri_admin`), so `DELETE`, `DROP` and `UPDATE`
work too. Prefer `SELECT`.
