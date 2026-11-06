#!/usr/bin/env bash
# Build build/agent.zip for AgentCore Runtime direct code deployment (Python 3.12, arm64):
# dependencies and main.py at the zip root, plus askwri/agent. Run before terraform plan.
set -euo pipefail

repo="$(cd "$(dirname "$0")/../.." && pwd)"
out="$repo/build/agent"
rm -rf "$out" "$repo/build/agent.zip"
mkdir -p "$out/askwri"

uv pip install --quiet --target "$out" --python-version 3.12 \
  --python-platform aarch64-manylinux2014 --only-binary :all: \
  "anthropic[bedrock]>=2.4.0" "boto3>=1.43" "opentelemetry-api>=1.30" \
  "aws-opentelemetry-distro>=0.18.0"
cp "$repo/askwri/__init__.py" "$out/askwri/"
cp -R "$repo/askwri/agent" "$out/askwri/"
# OpenTelemetry starts inside main.py rather than through the opentelemetry-instrument
# launcher, whose generated script points at the build machine's Python.
cat > "$out/main.py" <<'EOF'
"""AgentCore Runtime entry point: start ADOT tracing, then serve the agent on port 8080."""

from opentelemetry.instrumentation.auto_instrumentation import initialize

initialize()

from askwri.agent.server import serve  # noqa: E402 - must import after tracing starts

serve()
EOF
find "$out" -name "__pycache__" -type d -prune -exec rm -rf {} +

# AgentCore Runtime needs 644 on files and 755 on directories and executables.
find "$out" -type d -exec chmod 755 {} +
find "$out" -type f -exec chmod 644 {} +
[ -d "$out/bin" ] && chmod 755 "$out"/bin/*
# Fixed timestamps keep the zip byte-identical across builds, so Terraform only redeploys on change.
find "$out" -exec touch -t 202601010000 {} +
(cd "$out" && zip -qrX "$repo/build/agent.zip" .)
echo "Built build/agent.zip ($(du -h "$repo/build/agent.zip" | cut -f1))"
