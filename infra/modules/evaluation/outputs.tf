output "online_evaluation_config_arn" {
  description = "AgentCore online evaluation of live traffic."
  value       = aws_bedrockagentcore_online_evaluation_config.live.online_evaluation_config_arn
}

output "dashboard_name" {
  description = "CloudWatch dashboard for quality and operations."
  value       = aws_cloudwatch_dashboard.quality.dashboard_name
}
