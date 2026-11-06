#!/usr/bin/env bash
# Build build/api.zip for the askwri-api Lambda (Python 3.12, arm64, Lambda Web Adapter):
# askwri/api, a current boto3 (the runtime's may lack the bedrock-agentcore client) and run.sh,
# the handler the adapter starts. Run before terraform plan.
set -euo pipefail

repo="$(cd "$(dirname "$0")/../.." && pwd)"
out="$repo/build/api"
rm -rf "$out" "$repo/build/api.zip"
mkdir -p "$out/askwri"

uv pip install --quiet --target "$out" --python-version 3.12 \
  --python-platform aarch64-manylinux2014 --only-binary :all: "boto3>=1.43"
cp "$repo/askwri/__init__.py" "$out/askwri/"
cp -R "$repo/askwri/api" "$out/askwri/"
printf '#!/bin/sh\nexec python -m askwri.api\n' > "$out/run.sh"
find "$out" -name "__pycache__" -type d -prune -exec rm -rf {} +
find "$out" -type d -exec chmod 755 {} +
find "$out" -type f -exec chmod 644 {} +
chmod 755 "$out/run.sh"
find "$out" -exec touch -t 202601010000 {} +
(cd "$out" && zip -qrX "$repo/build/api.zip" .)
echo "Built build/api.zip ($(du -h "$repo/build/api.zip" | cut -f1))"
