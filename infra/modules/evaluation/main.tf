# Evaluation and operations: every trace indexed, AgentCore judges on live traffic, and the
# askwri-quality CloudWatch dashboard (eval scorecard from eval/run_eval.py plus live metrics
# the agent publishes under AskWRI/Live). Eval runs are judged in batch by eval/run_eval.py.

locals {
  runtime_log_group = "/aws/bedrock-agentcore/runtimes/${var.agent_runtime_id}-DEFAULT"
  judges = [
    "Builtin.Faithfulness",
    "Builtin.Helpfulness",
    "Builtin.ResponseRelevance",
    "Builtin.Refusal",
    "Builtin.ToolSelectionAccuracy",
  ]
}

# Transaction Search indexes 1% of spans by default; evaluation needs every span. The Default
# rule always exists, so it is imported rather than created.
import {
  to = aws_xray_indexing_rule.default
  id = "Default"
}

resource "aws_xray_indexing_rule" "default" {
  name = "Default"
  rule {
    probabilistic {
      desired_sampling_percentage = 100
    }
  }
}

data "aws_iam_policy_document" "evaluations_trust" {
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
  }
}

resource "aws_iam_role" "evaluations" {
  name               = "askwri-eval-role"
  description        = "AgentCore Evaluations: read askwri_agent traces, call judge models, write results."
  assume_role_policy = data.aws_iam_policy_document.evaluations_trust.json
}

data "aws_iam_policy_document" "evaluations" {
  statement {
    sid     = "ReadAgentTraces"
    actions = ["logs:StartQuery", "logs:GetQueryResults", "logs:FilterLogEvents", "logs:GetLogEvents", "logs:DescribeLogStreams"]
    resources = [
      "arn:aws:logs:${var.region}:${var.account_id}:log-group:aws/spans:*",
      "arn:aws:logs:${var.region}:${var.account_id}:log-group:${local.runtime_log_group}:*",
    ]
  }
  statement {
    sid       = "QueryResults"
    actions   = ["logs:GetQueryResults", "logs:StopQuery", "logs:DescribeLogGroups"]
    resources = ["*"]
  }
  statement {
    sid       = "WriteResults"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
    resources = ["arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/bedrock-agentcore/evaluations/*"]
  }
  statement {
    sid       = "JudgeModels"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = ["arn:aws:bedrock:*::foundation-model/*", "arn:aws:bedrock:*:${var.account_id}:inference-profile/*"]
  }
  statement {
    sid       = "ResultMetrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringLike"
      variable = "cloudwatch:namespace"
      values   = ["*AgentCore*", "*agentcore*"]
    }
  }
}

resource "aws_iam_role_policy" "evaluations" {
  name   = "askwri-eval"
  role   = aws_iam_role.evaluations.id
  policy = data.aws_iam_policy_document.evaluations.json
}

resource "aws_bedrockagentcore_online_evaluation_config" "live" {
  online_evaluation_config_name = "askwri_live"
  description                   = "Judges a sample of live AskWRI sessions with AgentCore's built-in evaluators."
  evaluation_execution_role_arn = aws_iam_role.evaluations.arn
  enable_on_create              = true

  data_source_config {
    cloudwatch_logs {
      log_group_names = ["aws/spans", local.runtime_log_group]
      service_names   = [var.agent_service_name]
    }
  }

  dynamic "evaluator" {
    for_each = toset(local.judges)
    content {
      evaluator_id = evaluator.value
    }
  }

  rule {
    sampling_config {
      sampling_percentage = var.online_eval_sampling_percentage
    }
    session_config {
      session_timeout_minutes = 15
    }
  }

  depends_on = [aws_iam_role_policy.evaluations, aws_xray_indexing_rule.default]
}

locals {
  live = "AskWRI/Live"
  eval = "AskWRI/Eval"
  # Eval scorecard tiles: the latest run's value of each metric.
  scorecard = [
    ["RecallAt5", "Recall@5 (target 0.75)"],
    ["PrecisionAt5", "Precision@5"],
    ["PageHitRate", "Cited page matches"],
    ["MustIncludeRate", "Expected figures in answer"],
    ["DeclineAccuracy", "Decline accuracy (target 1.0)"],
    ["VerifiedRate", "Claims verified / drafted"],
    ["AudienceAccuracy", "Reader inferred correctly"],
    ["MedianSecondsQuick", "Median s, Quick (target < 60)"],
    ["MedianSecondsDeep", "Median s, Deep (target < 60)"],
    ["EstimatedCostPerQuestionUSD", "Est. cost per question, USD"],
  ]
  user = "Source=\"user\""
}

resource "aws_cloudwatch_dashboard" "quality" {
  dashboard_name = "askwri-quality"
  dashboard_body = jsonencode({
    widgets = concat(
      [{
        type = "text", x = 0, y = 0, width = 24, height = 3,
        properties = {
          markdown = join("\n", [
            "# AskWRI: is it trustworthy, and is it cheap and healthy to run?",
            "**Evaluation scorecard**: latest run of `uv run python -m eval.run_eval run` (judged scores: `eval.run_eval judge`). **Live**: every answer's metrics from the agent (`AskWRI/Live`, user traffic). Costs are *estimated* from tokens and a price table.",
            "AgentCore judges on live traffic: [GenAI Observability → Evaluations](https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#gen-ai-observability/agent-core)",
          ])
        }
      }],
      [for i, metric in local.scorecard : {
        type = "metric", x = (i % 5) * 4 + (i < 5 ? 0 : 0), y = 3 + floor(i / 5) * 4, width = 4, height = 4,
        properties = {
          title     = metric[1], view = "singleValue", region = var.region, stat = "Average", period = 300,
          sparkline = true, setPeriodToTimeRange = false,
          metrics   = [[local.eval, metric[0]]]
        }
      }],
      [
        {
          type = "metric", x = 0, y = 11, width = 8, height = 6,
          properties = {
            title   = "Questions per hour (users)", view = "timeSeries", region = var.region, stat = "Sum", period = 3600,
            metrics = [[{ expression = "SEARCH('{${local.live},Mode,Source} MetricName=\"Questions\" ${local.user}', 'Sum', 3600)", id = "q", label = "" }]]
          }
        },
        {
          type = "metric", x = 8, y = 11, width = 8, height = 6,
          properties = {
            title       = "Time to answer, median by mode (s)", view = "timeSeries", region = var.region, period = 3600,
            metrics     = [[{ expression = "SEARCH('{${local.live},Mode,Source} MetricName=\"LatencySeconds\" ${local.user}', 'p50', 3600)", id = "l", label = "" }]],
            annotations = { horizontal = [{ label = "1 minute target", value = 60 }] }
          }
        },
        {
          type = "metric", x = 16, y = 11, width = 8, height = 6,
          properties = {
            title   = "Estimated spend per day, USD (users)", view = "bar", region = var.region, period = 86400,
            metrics = [[{ expression = "SUM(SEARCH('{${local.live},Mode,Source} MetricName=\"EstimatedCostUSD\" ${local.user}', 'Sum', 86400))", id = "c", label = "estimated USD" }]]
          }
        },
        {
          type = "metric", x = 0, y = 17, width = 8, height = 6,
          properties = {
            title = "Tokens per hour (in, out)", view = "timeSeries", region = var.region, period = 3600,
            metrics = [
              [{ expression = "SUM(SEARCH('{${local.live},Mode,Source} MetricName=\"TokensIn\"', 'Sum', 3600))", id = "ti", label = "input" }],
              [{ expression = "SUM(SEARCH('{${local.live},Mode,Source} MetricName=\"TokensOut\"', 'Sum', 3600))", id = "to", label = "output" }],
            ]
          }
        },
        {
          type = "metric", x = 8, y = 17, width = 8, height = 6,
          properties = {
            title = "Quality as usage grows: declined share, claims removed per answer", view = "timeSeries", region = var.region, period = 3600,
            metrics = [
              [{ expression = "SUM(SEARCH('{${local.live},Mode,Source} MetricName=\"Declined\" ${local.user}', 'Sum', 3600))", id = "d", visible = false }],
              [{ expression = "SUM(SEARCH('{${local.live},Mode,Source} MetricName=\"ClaimsRemoved\" ${local.user}', 'Sum', 3600))", id = "r", visible = false }],
              [{ expression = "SUM(SEARCH('{${local.live},Mode,Source} MetricName=\"Questions\" ${local.user}', 'Sum', 3600))", id = "n", visible = false }],
              [{ expression = "d / n", id = "dr", label = "declined share" }],
              [{ expression = "r / n", id = "rr", label = "claims removed per answer" }],
            ]
          }
        },
        {
          type = "metric", x = 16, y = 17, width = 8, height = 6,
          properties = {
            title   = "Failed answers (all traffic)", view = "timeSeries", region = var.region, period = 3600,
            metrics = [[{ expression = "SUM(SEARCH('{${local.live},Mode,Source} MetricName=\"Failed\"', 'Sum', 3600))", id = "f", label = "failed" }]]
          }
        },
      ],
    )
  })
}
