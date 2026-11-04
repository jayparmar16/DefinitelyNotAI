# The six tool Lambdas (askwri-tool-*) and askwri-tools-role. They run in the private app
# subnets and reach Aurora (IAM database auth as askwri_tools) and Bedrock through endpoints.

locals {
  tools = {
    search    = { handler = "askwri.tools.search.handler", memory = 1024 }
    passage   = { handler = "askwri.tools.passage.handler", memory = 512 }
    coverage  = { handler = "askwri.tools.coverage.handler", memory = 512 }
    authors   = { handler = "askwri.tools.authors.handler", memory = 512 }
    translate = { handler = "askwri.tools.translate.handler", memory = 512 }
    links     = { handler = "askwri.tools.links.handler", memory = 512 }
  }
  # A global inference profile routes to the model in any region, so both ARNs are needed.
  translate_profile_arn = "arn:aws:bedrock:${var.region}:${var.account_id}:inference-profile/${var.translate_model_id}"
  translate_model_arns = [
    "arn:aws:bedrock:*::foundation-model/${trimprefix(var.translate_model_id, "global.")}",
    "arn:aws:bedrock:::foundation-model/${trimprefix(var.translate_model_id, "global.")}",
  ]
  rerank_model_arn = "arn:aws:bedrock:${var.region}::foundation-model/${var.rerank_model_id}"
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "tools" {
  name               = "askwri-tools-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# Logs, plus the network interfaces a Lambda needs to run inside a VPC.
resource "aws_iam_role_policy_attachment" "vpc_access" {
  role       = aws_iam_role.tools.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "tools" {
  statement {
    sid       = "ConnectAsToolsUser"
    actions   = ["rds-db:connect"]
    resources = ["arn:aws:rds-db:${var.region}:${var.account_id}:dbuser:${var.db_cluster_resource_id}/askwri_tools"]
  }
  # Cohere Embed v4 runs through the "us." cross-region inference profile, which may serve a
  # call from any of the profile's regions: allow the profile and the model in each of them.
  statement {
    sid     = "EmbedQueries"
    actions = ["bedrock:InvokeModel"]
    resources = concat(
      ["arn:aws:bedrock:${var.region}:${var.account_id}:inference-profile/${var.embedding_model_id}"],
      [for r in ["us-east-1", "us-east-2", "us-west-2"] : "arn:aws:bedrock:${r}::foundation-model/${trimprefix(var.embedding_model_id, "us.")}"],
    )
  }
  statement {
    sid       = "Rerank"
    actions   = ["bedrock:InvokeModel"]
    resources = [local.rerank_model_arn]
  }
  statement {
    sid       = "RerankApi"
    actions   = ["bedrock:Rerank"] # the Rerank action has no resource-level permissions
    resources = ["*"]
  }
  statement {
    sid       = "Translate"
    actions   = ["bedrock:InvokeModel"]
    resources = concat([local.translate_profile_arn], local.translate_model_arns)
  }
}

resource "aws_iam_role_policy" "tools" {
  name   = "askwri-tools"
  role   = aws_iam_role.tools.id
  policy = data.aws_iam_policy_document.tools.json
}

resource "aws_cloudwatch_log_group" "tool" {
  for_each          = local.tools
  name              = "/aws/lambda/askwri-tool-${each.key}"
  retention_in_days = 7
}

resource "aws_lambda_function" "tool" {
  for_each         = local.tools
  function_name    = "askwri-tool-${each.key}"
  role             = aws_iam_role.tools.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = each.value.handler
  filename         = var.package_path
  source_code_hash = filebase64sha256(var.package_path)
  memory_size      = each.value.memory
  # Above Aurora's resume time after an auto-pause (15-30 s), plus the tool's own work.
  timeout = 90

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [var.security_group_id]
  }

  environment {
    variables = {
      DB_HOST                 = var.db_host
      DB_NAME                 = var.db_name
      DB_USER                 = "askwri_tools"
      ASKWRI_EMBEDDING_MODEL  = var.embedding_model_id
      ASKWRI_RERANK_MODEL_ARN = local.rerank_model_arn
      ASKWRI_TRANSLATE_MODEL  = var.translate_model_id
    }
  }

  depends_on = [aws_cloudwatch_log_group.tool, aws_iam_role_policy_attachment.vpc_access]
}
