#!/usr/bin/env bash
# Build build/tools.zip for the tool Lambdas (Python 3.12, arm64): askwri/tools and
# askwri/embed.py plus psycopg. boto3 comes with the Lambda runtime. Run before terraform plan.
set -euo pipefail

repo="$(cd "$(dirname "$0")/../.." && pwd)"
out="$repo/build/tools"
rm -rf "$out" "$repo/build/tools.zip"
mkdir -p "$out/askwri"

uv pip install --quiet --target "$out" --python-version 3.12 \
  --python-platform aarch64-manylinux_2_28 --only-binary :all: "psycopg[binary]>=3.2"
cp "$repo/askwri/__init__.py" "$repo/askwri/embed.py" "$out/askwri/"
cp -R "$repo/askwri/tools" "$out/askwri/"
find "$out" -name "__pycache__" -type d -prune -exec rm -rf {} +

# Fixed timestamps keep the zip byte-identical across builds, so Terraform only redeploys on change.
find "$out" -exec touch -t 202601010000 {} +
(cd "$out" && zip -qrX "$repo/build/tools.zip" .)
echo "Built build/tools.zip ($(du -h "$repo/build/tools.zip" | cut -f1))"
