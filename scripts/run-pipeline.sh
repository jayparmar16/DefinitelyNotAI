#!/usr/bin/env bash
# Whole ingestion run in one command. On the first run it creates the AWS resources with
# Terraform (state bucket, network, corpus bucket, Aurora); every run applies the schema
# (idempotent) and loads the PDFs in the given folders into Aurora.
# Usage: scripts/run-pipeline.sh [--reload] 2024 2025 2026  (one corpus folder per year)
set -euo pipefail
cd "$(dirname "$0")/.."

account="$(aws sts get-caller-identity --query Account --output text)"
export TF_VAR_team_account_id="$account"
export TF_VAR_team="${TF_VAR_team:-DefinitelyNotAI}"
export TF_VAR_owner="${TF_VAR_owner:-$(git config user.email)}"
export TF_VAR_db_min_capacity="${TF_VAR_db_min_capacity:-0.5}"  # 0.5 for the demo (#24)
# Same name as infra/modules/storage.
export CORPUS_BUCKET="askwri-corpus-$account"

if ! aws rds describe-db-clusters --db-cluster-identifier askwri-db >/dev/null 2>&1 \
  || ! aws s3api head-bucket --bucket "$CORPUS_BUCKET" >/dev/null 2>&1; then
  echo "AWS resources missing: creating them with Terraform"
  bash infra/bootstrap/create-state-bucket.sh
  terraform -chdir=infra init -input=false -backend-config=backend.hcl
  terraform -chdir=infra apply -input=false -auto-approve
fi

uv run python db/apply_schema.py
uv run python -m askwri.ingest.load "$@"
