#!/usr/bin/env bash
# One-time setup: create the Terraform state bucket in the team account and write
# infra/backend.hcl (gitignored). Safe to rerun. Refuses to run against any other account.
set -euo pipefail

region="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
account="$(aws sts get-caller-identity --query Account --output text)"

if [[ "${TF_VAR_team_account_id:-}" != "$account" ]]; then
  echo "Signed in to account $account, but TF_VAR_team_account_id is '${TF_VAR_team_account_id:-}'." >&2
  echo "Set TF_VAR_team_account_id to the team account and sign in to it." >&2
  exit 1
fi

bucket="askwri-tfstate-$account"

if aws s3api head-bucket --bucket "$bucket" 2>/dev/null; then
  echo "State bucket $bucket already exists"
else
  aws s3api create-bucket --bucket "$bucket" --region "$region" \
    --create-bucket-configuration "LocationConstraint=$region" >/dev/null
  echo "Created state bucket $bucket"
fi

aws s3api put-bucket-versioning --bucket "$bucket" \
  --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket "$bucket" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-encryption --bucket "$bucket" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-bucket-tagging --bucket "$bucket" --tagging \
  'TagSet=[{Key=Project,Value=AskWRI},{Key=Environment,Value=hackathon},{Key=ManagedBy,Value=bootstrap}]'

cat > "$(dirname "$0")/../backend.hcl" <<EOF
bucket       = "$bucket"
key          = "askwri/terraform.tfstate"
region       = "$region"
encrypt      = true
use_lockfile = true
EOF
echo "Wrote infra/backend.hcl. Next: cd infra && terraform init -backend-config=backend.hcl"
