#!/usr/bin/env bash
# Build the UI against the deployed askwri-api and publish it to askwri-web (S3 + CloudFront).
# Run after `terraform apply`, with AWS_PROFILE set to the team account. The build gets the API URL
# and the Cognito sign-in settings (all public); the API key stays server-side.
set -euo pipefail

cd "$(dirname "$0")/.."
output() { terraform -chdir=infra output -raw "$1"; }

bucket=$(output web_bucket)
distribution=$(output web_distribution_id)
export NEXT_PUBLIC_ASKWRI_API_URL=$(output api_url)
export NEXT_PUBLIC_ASKWRI_AUTH_DOMAIN=$(output login_domain)
export NEXT_PUBLIC_ASKWRI_AUTH_CLIENT_ID=$(output user_pool_client_id)
unset NEXT_PUBLIC_ASKWRI_API_KEY

# The topic spaces' publication counts, read by the sidebar (web/public is copied into the build).
mkdir -p web/public
uv run python -m askwri.spaces > web/public/spaces.json

(cd web && npm ci --silent && npm run build)

# Hashed assets never change; pages must be re-fetched after every deploy.
aws s3 sync web/out "s3://$bucket" --delete --only-show-errors --exclude "*" --include "_next/static/*" \
  --cache-control "public,max-age=31536000,immutable"
aws s3 sync web/out "s3://$bucket" --delete --only-show-errors --exclude "_next/static/*" \
  --cache-control "no-cache"
aws cloudfront create-invalidation --distribution-id "$distribution" --paths "/*" \
  --query Invalidation.Id --output text

echo "Published: $(output web_url)  (admin: $(output web_url)/admin/)"
