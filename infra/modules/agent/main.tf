# The AskWRI agent on AgentCore Runtime (askwri_agent), its memory, guardrail and role, and the
# account's CloudWatch Transaction Search so agent traces reach CloudWatch.
# Runtime and memory names allow letters, digits and underscores only, so they use "_".

locals {
  runtime_name = "askwri_agent"
  # Global inference profiles route to the model in any region: allow the profile and the model.
  model_arns = flatten([
    for id in [var.small_model_id, var.large_model_id] : [
      "arn:aws:bedrock:${var.region}:${var.account_id}:inference-profile/${id}",
      "arn:aws:bedrock:*::foundation-model/${replace(id, "/^(global|us)\\./", "")}",
      "arn:aws:bedrock:::foundation-model/${replace(id, "/^(global|us)\\./", "")}",
    ]
  ])
  package_key = "agent/${filesha256(var.package_path)}.zip"
}

# --- Where the code package lives ---

resource "aws_s3_bucket" "artifacts" {
  bucket = "askwri-artifacts-${var.account_id}"
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# The key holds the package's hash, so a new build is a new object and the runtime redeploys.
resource "aws_s3_object" "package" {
  bucket     = aws_s3_bucket.artifacts.id
  key        = local.package_key
  source     = var.package_path
  depends_on = [aws_s3_bucket_public_access_block.artifacts]
}

# --- Memory and guardrail ---

resource "aws_bedrockagentcore_memory" "askwri" {
  name                  = "askwri_memory"
  description           = "Short-term conversation memory: questions and answers per session."
  event_expiry_duration = 7
}

resource "aws_bedrock_guardrail" "askwri" {
  name                      = "askwri-guardrail"
  description               = "Contextual grounding check on every AskWRI answer."
  blocked_input_messaging   = "AskWRI can't help with that request."
  blocked_outputs_messaging = "AskWRI couldn't verify this answer against WRI's publications."

  # Grounding only. Its relevance filter scores each part of an answer against the whole
  # question, and a Deep research key point answers one sub-question: a fully grounded point
  # scored 0.06. Relevance is settled earlier, by the reranker and the drafter.
  contextual_grounding_policy_config {
    filters_config {
      type      = "GROUNDING"
      threshold = var.grounding_threshold
    }
  }
}

# The agent uses a published version, which is frozen: changing the guardrail only edits its
# draft. Replacing the version whenever the guardrail changes publishes the new settings.
resource "aws_bedrock_guardrail_version" "askwri" {
  guardrail_arn = aws_bedrock_guardrail.askwri.guardrail_arn
  description   = "Used by askwri_agent"

  lifecycle {
    replace_triggered_by = [aws_bedrock_guardrail.askwri]
  }
}

# --- The agent's role ---

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:bedrock-agentcore:${var.region}:${var.account_id}:*"]
    }
  }
}

resource "aws_iam_role" "agent" {
  name               = "askwri-agent-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "agent" {
  statement {
    sid       = "ReadCodePackage"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/agent/*"]
  }
  statement {
    sid       = "RuntimeLogs"
    actions   = ["logs:DescribeLogStreams", "logs:CreateLogGroup"]
    resources = ["arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"]
  }
  statement {
    sid       = "SpansInAgentLogGroup"
    actions   = ["logs:PutResourcePolicy"]
    resources = ["arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/bedrock-agentcore/runtimes/${local.runtime_name}-*"]
  }
  statement {
    sid       = "DescribeLogGroups"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["arn:aws:logs:${var.region}:${var.account_id}:log-group:*"]
  }
  statement {
    sid       = "WriteLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"]
  }
  statement {
    sid       = "Traces"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"]
    resources = ["*"] # X-Ray actions have no resource-level permissions
  }
  statement {
    sid       = "Metrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["bedrock-agentcore"]
    }
  }
  statement {
    sid = "WorkloadIdentity"
    actions = [
      "bedrock-agentcore:GetWorkloadAccessToken",
      "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
      "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
    ]
    resources = [
      "arn:aws:bedrock-agentcore:${var.region}:${var.account_id}:workload-identity-directory/default",
      "arn:aws:bedrock-agentcore:${var.region}:${var.account_id}:workload-identity-directory/default/workload-identity/${local.runtime_name}-*",
    ]
  }
  statement {
    sid       = "Models"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = local.model_arns
  }
  statement {
    sid       = "Guardrail"
    actions   = ["bedrock:ApplyGuardrail"]
    resources = [aws_bedrock_guardrail.askwri.guardrail_arn]
  }
  statement {
    sid       = "GatewayCredentials"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.gateway_secret_arn]
  }
  statement {
    sid       = "Memory"
    actions   = ["bedrock-agentcore:CreateEvent", "bedrock-agentcore:ListEvents", "bedrock-agentcore:GetEvent"]
    resources = [aws_bedrockagentcore_memory.askwri.arn]
  }
}

resource "aws_iam_role_policy" "agent" {
  name   = "askwri-agent"
  role   = aws_iam_role.agent.id
  policy = data.aws_iam_policy_document.agent.json
}

# --- The runtime ---

resource "aws_bedrockagentcore_agent_runtime" "askwri" {
  agent_runtime_name = local.runtime_name
  description        = "AskWRI: cited answers and research reports from WRI publications"
  role_arn           = aws_iam_role.agent.arn

  agent_runtime_artifact {
    code_configuration {
      entry_point = ["main.py"] # main.py starts ADOT tracing itself
      runtime     = "PYTHON_3_12"
      code {
        s3 {
          bucket = aws_s3_bucket.artifacts.id
          prefix = aws_s3_object.package.key
        }
      }
    }
  }

  network_configuration {
    network_mode = "PUBLIC" # data access goes through the gateway, never directly
  }

  lifecycle_configuration {
    idle_runtime_session_timeout = 900
    max_lifetime                 = 3600
  }

  environment_variables = {
    AWS_DEFAULT_REGION         = var.region
    ASKWRI_GATEWAY_URL         = var.gateway_url
    ASKWRI_GATEWAY_SECRET      = var.gateway_secret_name
    ASKWRI_MEMORY_ID           = aws_bedrockagentcore_memory.askwri.id
    ASKWRI_SMALL_MODEL         = var.small_model_id
    ASKWRI_LARGE_MODEL         = var.large_model_id
    ASKWRI_RELEVANCE_THRESHOLD = tostring(var.relevance_threshold)
    ASKWRI_QUICK_ROUNDS        = tostring(var.quick_max_rounds)
    ASKWRI_DEEP_ROUNDS         = tostring(var.deep_max_rounds)
    ASKWRI_GUARDRAIL_ID        = aws_bedrock_guardrail.askwri.guardrail_id
    ASKWRI_GUARDRAIL_VERSION   = aws_bedrock_guardrail_version.askwri.version
  }

  depends_on = [aws_iam_role_policy.agent]
}

# --- CloudWatch Transaction Search (account-wide, one-time) ---
# Lets X-Ray write spans to CloudWatch Logs, then sends trace segments there. Without it no
# agent spans reach CloudWatch, and AgentCore Evaluations has nothing to score.

data "aws_iam_policy_document" "transaction_search" {
  statement {
    actions = ["logs:PutLogEvents"]
    principals {
      type        = "Service"
      identifiers = ["xray.amazonaws.com"]
    }
    resources = [
      "arn:aws:logs:${var.region}:${var.account_id}:log-group:aws/spans:*",
      "arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/application-signals/data:*",
    ]
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:xray:${var.region}:${var.account_id}:*"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_id]
    }
  }
}

resource "aws_cloudwatch_log_resource_policy" "transaction_search" {
  policy_name     = "askwri-transaction-search"
  policy_document = data.aws_iam_policy_document.transaction_search.json
}

resource "aws_xray_trace_segment_destination" "cloudwatch" {
  destination = "CloudWatchLogs"
  depends_on  = [aws_cloudwatch_log_resource_policy.transaction_search]
}
