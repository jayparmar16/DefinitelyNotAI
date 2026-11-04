# Terraform support for AgentCore Runtime and Memory

Research for issue #36. As of 2026-11-04. Provider docs are read at tag `v6.71.0`, the version
`infra/.terraform.lock.hcl` locks on branch `askwri-infra-backend`.

## Recommendation for the demo

**Yes, Terraform can create both, and the team's pinned provider is new enough.** `hashicorp/aws`
added `aws_bedrockagentcore_agent_runtime` and `aws_bedrockagentcore_agent_runtime_endpoint` in
6.17.0 and `aws_bedrockagentcore_memory` in 6.18.0 (October 2025). `infra/versions.tf` pins
`~> 6.71` and the lock file has 6.71.0, so no provider upgrade is needed.

For tomorrow:

1. **Deploy the agent as direct code (a zip in S3), not a container.** The runtime has taken a
   zip through `agent_runtime_artifact.code_configuration` since 6.22.0, with `PYTHON_3_12` as a
   valid runtime. Our agent needs only boto3 (Bedrock, the RDS Data API, AgentCore Memory), and
   boto3 is pure Python, so the zip builds on any laptop. That means no Docker, no `buildx`, no
   arm64 emulation and no ECR repository. AWS also says updates deploy faster than container
   updates. One script builds the zip and runs `terraform apply`. Terraform uploads the zip and
   rolls out a new runtime version in the same apply.
2. **Create one `aws_bedrockagentcore_memory` with no strategies.** A memory with no strategies
   keeps short-term memory only (raw events), which is what follow-ups need. Set
   `event_expiry_duration = 7`, the minimum.
3. **Don't create an `aws_bedrockagentcore_agent_runtime_endpoint`.** The `DEFAULT` endpoint
   exists automatically and always points to the latest version. Invoke with
   `qualifier = "DEFAULT"`.
4. **Don't use the AgentCore CLI or the starter toolkit.** The AgentCore CLI
   (`npm install -g @aws/agentcore`) deploys through CDK and CloudFormation, which would create a
   second infrastructure stack next to Terraform. The Python `bedrock-agentcore-starter-toolkit`
   is deprecated.
5. **Keep the container path as the fallback.** Switch to it only if a dependency ships native
   code without an aarch64 wheel, or if the package grows past 250 MB zipped. The steps are below.

Gotchas that would cost time tomorrow:

- **Names allow letters, digits and underscores only** (`[a-zA-Z][a-zA-Z0-9_]{0,47}`) for both the
  runtime and the memory. The solution design's `askwri-agent-runtime` and `askwri-memory` fail
  validation. Use `askwri_agent` and `askwri_memory`.
- **Every rollout must change an argument.** Terraform calls `UpdateAgentRuntime` only when the
  configuration changes. Re-uploading the zip to the same key, or re-pushing `:latest`, produces
  no diff and no new version. Put a content hash in the S3 key, or a git SHA in the image tag.
- **Build the zip (or push the image) before `terraform apply`.** `filemd5()` reads the zip at plan
  time, and creating a runtime fails if the artifact doesn't exist yet.
- **The identity that runs Terraform needs `s3:GetObject` on the zip.** AgentCore reads it with the
  caller's credentials when it creates or updates the runtime. The deployer role is already in the
  corpus bucket's `object_roles`, so an `agent-code/` prefix in that bucket works as it stands.
- **`lifecycle_configuration`: set both values or neither.** If you set only `max_lifetime`, apply
  fails with "inconsistent result after apply" (open provider issue
  [#45290](https://github.com/hashicorp/terraform-provider-aws/issues/45290)).
- **Changing `agent_runtime_name`, or switching between code and container, replaces the runtime.**
  That gives it a new ARN, so the API Lambda's `AGENT_RUNTIME_ARN` must come from the Terraform
  output, not be typed in by hand.
- **Terraform doesn't manage the runtime's log group.** The service creates
  `/aws/bedrock-agentcore/runtimes/...` itself, so Terraform can't set its retention
  ([#47629](https://github.com/hashicorp/terraform-provider-aws/issues/47629)).
- **`InvokeAgentRuntime` needs a `runtimeSessionId` of at least 33 characters.**

## Minimal Terraform for AskWRI

This would be added to `infra/` on `askwri-infra-backend`. It follows the v6.71.0 docs and the AWS
execution role reference, but hasn't been run through `terraform validate` because Terraform isn't
installed on the research machine. It assumes two new outputs on the database module,
`cluster_arn` and `secret_arn`. Today the module exports only `cluster_identifier`.

```hcl
locals {
  agent_name = "askwri_agent"                 # letters, digits, underscores only
  agent_zip  = "${path.module}/../build/agent.zip"
}

resource "aws_bedrockagentcore_memory" "askwri" {
  name                  = "askwri_memory"
  event_expiry_duration = 7                   # days, 7 to 365; no strategies = short-term only
}

# shortcut: agent code shares the corpus bucket - the deployer role already has object access
resource "aws_s3_object" "agent_code" {
  bucket = module.storage.corpus_bucket
  key    = "agent-code/${filemd5(local.agent_zip)}.zip" # new key per build = new runtime version
  source = local.agent_zip
}

data "aws_iam_policy_document" "agent_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.team_account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:bedrock-agentcore:${var.region}:${var.team_account_id}:*"]
    }
  }
}

data "aws_iam_policy_document" "agent" {
  statement {
    actions   = ["logs:CreateLogGroup", "logs:DescribeLogStreams"]
    resources = ["arn:aws:logs:${var.region}:${var.team_account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"]
  }
  statement {
    actions   = ["logs:DescribeLogGroups"]
    resources = ["arn:aws:logs:${var.region}:${var.team_account_id}:log-group:*"]
  }
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.region}:${var.team_account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"]
  }
  statement {
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"]
    resources = ["*"]
  }
  statement {
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["bedrock-agentcore"]
    }
  }
  statement {
    # Covers foundation models and the account's cross-region inference profiles.
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = [
      "arn:aws:bedrock:*::foundation-model/*",
      "arn:aws:bedrock:${var.region}:${var.team_account_id}:*",
    ]
  }
  statement {
    actions   = ["bedrock-agentcore:CreateEvent", "bedrock-agentcore:ListEvents", "bedrock-agentcore:GetEvent"]
    resources = [aws_bedrockagentcore_memory.askwri.arn]
  }
  statement {
    actions   = ["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement"]
    resources = [module.database.cluster_arn]
  }
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [module.database.secret_arn]
  }
}

resource "aws_iam_role" "agent" {
  name               = "askwri-agent-role"
  assume_role_policy = data.aws_iam_policy_document.agent_assume.json
}

resource "aws_iam_role_policy" "agent" {
  role   = aws_iam_role.agent.id
  policy = data.aws_iam_policy_document.agent.json
}

resource "aws_bedrockagentcore_agent_runtime" "askwri" {
  agent_runtime_name = local.agent_name
  role_arn           = aws_iam_role.agent.arn

  agent_runtime_artifact {
    code_configuration {
      entry_point = ["main.py"]
      runtime     = "PYTHON_3_12"
      code {
        s3 {
          bucket = aws_s3_object.agent_code.bucket
          prefix = aws_s3_object.agent_code.key # the object key, despite the name
        }
      }
    }
  }

  network_configuration {
    network_mode = "PUBLIC" # fine: data access goes through the RDS Data API, not the VPC
  }

  protocol_configuration {
    server_protocol = "HTTP"
  }

  environment_variables = {
    MEMORY_ID      = aws_bedrockagentcore_memory.askwri.id
    DB_CLUSTER_ARN = module.database.cluster_arn
    DB_SECRET_ARN  = module.database.secret_arn
  }

  # The policy must be attached before the runtime first assumes the role.
  depends_on = [aws_iam_role_policy.agent]
}

output "agent_runtime_arn" {
  description = "Pass to InvokeAgentRuntime with qualifier DEFAULT."
  value       = aws_bedrockagentcore_agent_runtime.askwri.agent_runtime_arn
}
```

The API Lambda's role needs `bedrock-agentcore:InvokeAgentRuntime` on the runtime. It calls
`invoke_agent_runtime(agentRuntimeArn=..., runtimeSessionId=<33+ chars>, qualifier="DEFAULT", payload=...)`
([custom agent tutorial](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/getting-started-custom.html)).

### Build and deploy script (direct code)

```sh
rm -rf build/agent build/agent.zip && mkdir -p build/agent
uv pip install --python-platform aarch64-manylinux2014 --python-version 3.12 \
  --only-binary=:all: --target build/agent boto3
cp -R askwri main.py build/agent/          # main.py (the HTTP server) must sit at the zip root
find build/agent -name __pycache__ -prune -exec rm -rf {} +
(cd build/agent && zip -qr ../agent.zip .)
terraform -chdir=infra apply
```

The `uv pip install` flags come from the AWS direct-deploy guide. Limits are 250 MB zipped and
750 MB unzipped. Files need mode 644 and directories 755. AWS recommends leaving out
`__pycache__` folders. Add `build/` to `.gitignore`, because it isn't listed today. Because zip timestamps change on every build, each deploy makes a new
runtime version even when the code hasn't changed. That's harmless.

### The agent's HTTP server (stdlib, no SDK)

Without Strands or the AgentCore SDK, the entry point only has to answer two routes on
`0.0.0.0:8080`:

```python
"""AgentCore Runtime entry point: serves POST /invocations and GET /ping on port 8080."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from askwri.agent import answer  # the team's agent loop

SESSION_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/ping":
            return self.send_error(404)
        self._send_json({"status": "Healthy"})

    def do_POST(self):
        if self.path != "/invocations":
            return self.send_error(404)
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._send_json(answer(request, session_id=self.headers.get(SESSION_HEADER)))

    def _send_json(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
```

The runtime session ID makes a natural AgentCore Memory `sessionId`. The SDK's own server reads
the same header on `/invocations`.

### Short-term memory calls from the agent

```python
import os
from datetime import UTC, datetime

import boto3

memory = boto3.client("bedrock-agentcore")
memory.create_event(
    memoryId=os.environ["MEMORY_ID"],
    actorId=user_id,
    sessionId=session_id,
    eventTimestamp=datetime.now(UTC),
    payload=[{"conversational": {"content": {"text": text}, "role": "USER"}}],  # or ASSISTANT
)
history = memory.list_events(
    memoryId=os.environ["MEMORY_ID"],
    actorId=user_id,
    sessionId=session_id,
    includePayloads=True,
)
```

## Fallback: container image

Use this only if the zip path fails. It adds an `aws_ecr_repository` and swaps the artifact block.
Switching from code to container replaces the runtime.

```hcl
resource "aws_ecr_repository" "agent" {
  name = "askwri-agent"
}

# in aws_bedrockagentcore_agent_runtime.askwri:
agent_runtime_artifact {
  container_configuration {
    container_uri = "${aws_ecr_repository.agent.repository_url}:${var.agent_image_tag}"
  }
}
```

The execution role also needs `ecr:BatchGetImage` and `ecr:GetDownloadUrlForLayer` on the
repository, plus `ecr:GetAuthorizationToken` on `*`.

```sh
terraform -chdir=infra apply -target=aws_ecr_repository.agent   # first deploy only
REPO=$(terraform -chdir=infra output -raw agent_repository_url)
TAG=$(git rev-parse --short HEAD)                                # immutable tag = a real rollout
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin "${REPO%%/*}"
docker buildx build --platform linux/arm64 -t "$REPO:$TAG" --push .
terraform -chdir=infra apply -var agent_image_tag="$TAG"
```

The image must be `linux/arm64`, listen on `0.0.0.0:8080` and serve the same two routes. AWS's
example Dockerfile starts `FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.11-bookworm-slim`.
Apple Silicon Macs build arm64 natively, while x86 machines emulate through `buildx`. The
container URI may also use a digest (`repo@sha256:...`).

## Facts and sources

### Provider resources and versions

From the [provider CHANGELOG](https://github.com/hashicorp/terraform-provider-aws/blob/main/CHANGELOG.md):

| Release | Date | Change |
| --- | --- | --- |
| 6.17.0 | 2025-10-16 | New resources `aws_bedrockagentcore_agent_runtime` and `aws_bedrockagentcore_agent_runtime_endpoint` (also `browser`, `code_interpreter`, `gateway`, `gateway_target`, `api_key_credential_provider`) |
| 6.18.0 | 2025-10-23 | New resources `aws_bedrockagentcore_memory` and `aws_bedrockagentcore_memory_strategy` (also `oauth2_credential_provider`, `token_vault_cmk`, `workload_identity`) |
| 6.22.0 | 2025-11-20 | Runtime: `agent_runtime_artifact.code_configuration` added; `container_configuration` made optional |
| 6.46.0 | 2026-05-20 | Runtime: `filesystem_configuration` |
| 6.50.0 | 2026-06-10 | Runtime: `AGUI` protocol; memory: `indexed_key`, `stream_delivery_resources` |
| 6.57.1 | 2026-07-29 | Memory strategy: `namespaces` and `memory_execution_role_arn` deprecated |
| 6.68.0 | 2026-10-07 | Runtime: `platform_version` (`V1`/`V2`) |
| 6.71.0 | 2026-10-28 | Latest release; the team's lock file version |

**`aws_bedrockagentcore_agent_runtime`**
([docs at v6.71.0](https://github.com/hashicorp/terraform-provider-aws/blob/v6.71.0/website/docs/r/bedrockagentcore_agent_runtime.html.markdown),
[Registry](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_agent_runtime)):

- Required: `agent_runtime_name`, `role_arn`, `agent_runtime_artifact` (exactly one of
  `container_configuration { container_uri }` or
  `code_configuration { entry_point, runtime, code { s3 { bucket, prefix, version_id? } } }`), and
  `network_configuration { network_mode = PUBLIC | VPC }`. `VPC` takes
  `network_mode_config { security_groups, subnets }`.
- Optional: `protocol_configuration.server_protocol` (`HTTP`, `MCP`, `A2A`, `AGUI`),
  `environment_variables`, `lifecycle_configuration` (`idle_runtime_session_timeout`,
  `max_lifetime`), `authorizer_configuration.custom_jwt_authorizer`,
  `request_header_configuration`, `filesystem_configuration`, `platform_version`, `tags`.
- Code `runtime` values: `PYTHON_3_10` to `PYTHON_3_14`, `NODE_22`.
- Exports `agent_runtime_arn`, `agent_runtime_id` and `agent_runtime_version`. Timeouts default
  to 30 minutes.
- In the [provider source](https://github.com/hashicorp/terraform-provider-aws/blob/v6.71.0/internal/service/bedrockagentcore/agent_runtime.go),
  `agent_runtime_name` is `RequiresReplace`, and so is a switch between `code_configuration` and
  `container_configuration`. Other changes, such as a new `container_uri`, S3 key, env vars or
  role, update the runtime in place through `UpdateAgentRuntime`.

**`aws_bedrockagentcore_agent_runtime_endpoint`**
([docs](https://github.com/hashicorp/terraform-provider-aws/blob/v6.71.0/website/docs/r/bedrockagentcore_agent_runtime_endpoint.html.markdown)):
requires `name` and `agent_runtime_id`, with an optional `agent_runtime_version` to pin.
AskWRI only needs it to pin a version.

**`aws_bedrockagentcore_memory`**
([docs](https://github.com/hashicorp/terraform-provider-aws/blob/v6.71.0/website/docs/r/bedrockagentcore_memory.html.markdown)):
requires `name` and `event_expiry_duration` (7 to 365 days). Optional arguments are `description`,
`encryption_key_arn` (AWS-managed encryption when omitted), `memory_execution_role_arn` (needed
only for strategies that call a model), `indexed_key`, `stream_delivery_resources` and `tags`.
Exports `id` and `arn`. Long-term strategies are a separate resource,
`aws_bedrockagentcore_memory_strategy`, which AskWRI doesn't need.

### Runtime contract (HTTP protocol)

From the [service contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html)
and the [HTTP protocol contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html):

- Host `0.0.0.0`, port 8080 for HTTP (MCP uses 8000 and `/mcp`, A2A uses 9000 and `/`). An ARM64
  container is required.
- `POST /invocations` takes JSON and returns JSON (`application/json`) or SSE
  (`text/event-stream`). WebSocket on `/ws` is optional.
- `GET /ping` returns `200` with `{"status": "Healthy"}`, or `"HealthyBusy"` while background work
  runs, which keeps the session alive. Don't set `time_of_last_update` on every ping, or the idle
  timeout never fires.
- The session ID arrives in the `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` header. The
  [SDK server](https://github.com/aws/bedrock-agentcore-sdk-python/blob/main/src/bedrock_agentcore/runtime/app.py)
  reads it on `/invocations`.
- Direct code still has to follow this contract, using either the SDK's `@app.entrypoint` or a
  server that implements both routes
  ([Python direct deploy](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-code-deploy-python.html)).

### Execution role

From [IAM permissions for AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html):

- Trust: `bedrock-agentcore.amazonaws.com`, conditioned on `aws:SourceAccount` and
  `aws:SourceArn`.
- The direct-deploy role needs CloudWatch Logs on `/aws/bedrock-agentcore/runtimes/*`, X-Ray,
  `cloudwatch:PutMetricData` (namespace `bedrock-agentcore`), and
  `bedrock:InvokeModel`/`InvokeModelWithResponseStream`. The container role also needs
  `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer` and `ecr:GetAuthorizationToken`.
- AWS's container role also grants `bedrock-agentcore:GetWorkloadAccessToken*`, which is only
  needed for AgentCore Identity (outbound OAuth, such as a Gateway token).
- Memory data-plane actions are `bedrock-agentcore:CreateEvent`, `ListEvents`, `GetEvent` and
  `DeleteEvent` on `memory/${MemoryId}`
  ([Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_bedrock-agentcore.html)).
- For a code zip, the identity calling Create/UpdateAgentRuntime needs `s3:GetObject` on the
  object, and `kms:Decrypt` if it's encrypted with a customer-managed key
  ([direct-deploy troubleshooting](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-code-deploy-common-issues.html)).

### Versions and rollout

From [Runtime versioning and endpoints](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agent-runtime-versioning.html):
creating a runtime makes version 1, and every update makes a new, immutable version. The `DEFAULT`
endpoint moves to the latest version automatically. Named endpoints stay where they are until
updated.

### Direct code compared with a container

From the [direct code deployment overview](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-code-deploy.html):

- Packages: 250 MB for a zip, up to 2 GB for a container.
- Session creation: 25 new sessions per second for direct code, 1.6 for containers.
- Updates are "significantly faster" with direct code.
- With direct code, AWS patches the managed runtime. With a container, the team rebuilds the image
  to pick up fixes.

### Region

US West (Oregon) supports AgentCore Runtime and Memory
([supported Regions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html)).

### Scripted alternatives

Terraform works, so these are escape hatches only.

- **boto3 / AWS CLI:** `bedrock-agentcore-control` `create_agent_runtime`, `update_agent_runtime`
  and `create_memory` take the same fields as the Terraform arguments
  ([custom agent tutorial](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/getting-started-custom.html),
  [Python direct deploy](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-code-deploy-python.html)).
  If the provider misbehaves tomorrow, create the runtime with a short boto3 script, then adopt it
  later with an `import` block (`id = <agent_runtime_id>`).
- **AgentCore CLI:** `@aws/agentcore` on npm, v1.0.1 released 2026-10-27
  ([repo](https://github.com/aws/agentcore-cli),
  [quickstart](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-get-started-cli.html)).
  It needs Node.js 20.12 or later, and `agentcore deploy` synthesizes a CDK app into a
  CloudFormation stack. It's reproducible, but it's a second IaC tool next to Terraform.
- **Starter toolkit:** the GitHub description of `aws/bedrock-agentcore-starter-toolkit` reads
  "DEPRECATED — Do not use this toolkit. Use the AgentCore CLI instead"
  ([repo](https://github.com/aws/bedrock-agentcore-starter-toolkit)).

### Open provider issues worth knowing

- [#45290](https://github.com/hashicorp/terraform-provider-aws/issues/45290): setting only
  `max_lifetime` in `lifecycle_configuration` gives an inconsistent result after apply.
- [#47629](https://github.com/hashicorp/terraform-provider-aws/issues/47629): the runtime's log
  group is created outside Terraform.
- [#45719](https://github.com/hashicorp/terraform-provider-aws/issues/45719): the `DEFAULT`
  endpoint's ARN isn't exported. Not needed, because invoking uses the runtime ARN plus
  `qualifier`.
- [#50352](https://github.com/hashicorp/terraform-provider-aws/issues/50352): parallel endpoint
  creates on one runtime conflict. Irrelevant if no named endpoints are created.
