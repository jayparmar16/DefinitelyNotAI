# askwri-api: the browser's way in. A Lambda Function URL with response streaming (API Gateway
# HTTP APIs stop at 30 s; Deep research takes about a minute) running askwri.api through the
# Lambda Web Adapter. Outside the VPC: it only calls AgentCore Runtime and presigns S3 links.

resource "aws_secretsmanager_secret" "api_key" {
  name                    = "askwri/api-key"
  description             = "Shared key the UI sends as X-AskWRI-Key."
  recovery_window_in_days = 0 # shortcut: immediate delete on destroy, so a redeploy can reuse the name
}

ephemeral "random_password" "api_key" {
  length  = 40
  special = false
}

resource "aws_secretsmanager_secret_version" "api_key" {
  secret_id                = aws_secretsmanager_secret.api_key.id
  secret_string_wo         = ephemeral.random_password.api_key.result
  secret_string_wo_version = 1
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api" {
  name               = "askwri-api-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "api" {
  statement {
    sid       = "InvokeAgent"
    actions   = ["bedrock-agentcore:InvokeAgentRuntime"]
    resources = [var.runtime_arn, "${var.runtime_arn}/*"]
  }
  statement {
    sid       = "PresignStoredPdfs"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${var.corpus_bucket}/raw/*"]
  }
  statement {
    sid       = "ReadApiKey"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.api_key.arn]
  }
  statement {
    sid       = "QueryLog"
    actions   = ["dynamodb:PutItem", "dynamodb:Query", "dynamodb:GetItem"]
    resources = [aws_dynamodb_table.query_log.arn]
  }
  statement {
    sid       = "ReadEvalResults"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${var.corpus_bucket}/eval/results/*"]
  }
  statement {
    sid       = "ListEvalResults"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.corpus_bucket}"]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["eval/results/*"]
    }
  }
}

# One record per question for the admin page: cost, tokens per step, latency, claims, sources.
# Partitioned by UTC day; records expire after 90 days.
resource "aws_dynamodb_table" "query_log" {
  name         = "askwri-query-log"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "day"
  range_key    = "sk"

  attribute {
    name = "day"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }
  ttl {
    attribute_name = "expires"
    enabled        = true
  }
  point_in_time_recovery {
    enabled = true
  }
  server_side_encryption {
    enabled = true
  }
}

resource "aws_iam_role_policy" "api" {
  name   = "askwri-api"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/askwri-api"
  retention_in_days = 7
}

resource "aws_lambda_function" "api" {
  function_name    = "askwri-api"
  role             = aws_iam_role.api.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "run.sh"
  filename         = var.package_path
  source_code_hash = filebase64sha256(var.package_path)
  layers           = [var.web_adapter_layer_arn]
  memory_size      = 512
  timeout          = 300 # Deep research runs about a minute; leave room for a cold agent session
  # Throttling: at most this many requests at once, so a leaked URL can't run up the bill.
  reserved_concurrent_executions = var.max_concurrency

  environment {
    variables = {
      AWS_LAMBDA_EXEC_WRAPPER      = "/opt/bootstrap"
      AWS_LWA_INVOKE_MODE          = "response_stream"
      AWS_LWA_READINESS_CHECK_PATH = "/ping"
      PORT                         = "8080"
      ASKWRI_RUNTIME_ARN           = var.runtime_arn
      ASKWRI_CORPUS_BUCKET         = var.corpus_bucket
      ASKWRI_ALLOWED_ORIGINS       = join(",", var.allowed_origins)
      ASKWRI_API_KEY_SECRET        = aws_secretsmanager_secret.api_key.name
      ASKWRI_USER_POOL_CLIENT_ID   = var.user_pool_client_id
      ASKWRI_QUERY_LOG_TABLE       = aws_dynamodb_table.query_log.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.api, aws_iam_role_policy.api, aws_secretsmanager_secret_version.api_key]
}

# Public URL; the app checks X-AskWRI-Key and CORS. AWS adds the two invoke permissions a
# NONE-auth URL needs when the URL is created.
resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE" # shortcut: shared key until the UI signs users in with Cognito
  invoke_mode        = "RESPONSE_STREAM"
}
