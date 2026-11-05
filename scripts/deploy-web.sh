#!/usr/bin/env bash
# Build the UI against the deployed askwri-api and publish it to askwri-web (S3 + CloudFront).
# Run after `terraform apply`, with AWS_PROFILE set to the team account. Writes no files outside
# web/out: the API URL and key go to the build as environment variables only.
set -euo pipefail

cd "$(dirname "$0")/.."
output() { terraform -chdir=infra output -raw "$1"; }

bucket=$(output web_bucket)
distribution=$(output web_distribution_id)
export NEXT_PUBLIC_ASKWRI_API_URL=$(output api_url)
export NEXT_PUBLIC_ASKWRI_API_KEY=$(aws secretsmanager get-secret-value \
  --secret-id "$(output api_key_secret)" --query SecretString --output text)

(cd web && npm ci --silent && npm run build)

# Hashed assets never change; pages must be re-fetched after every deploy.
aws s3 sync web/out "s3://$bucket" --delete --exclude "*" --include "_next/static/*" \
  --cache-control "public,max-age=31536000,immutable"
aws s3 sync web/out "s3://$bucket" --delete --exclude "_next/static/*" \
  --cache-control "no-cache"
aws cloudfront create-invalidation --distribution-id "$distribution" --paths "/*" \
  --query Invalidation.Id --output text

echo "Published: $(output web_url)  (admin: $(output web_url)/admin/)"
