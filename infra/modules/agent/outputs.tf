output "runtime_name" {
  description = "Name of the agent runtime."
  value       = aws_bedrockagentcore_agent_runtime.askwri.agent_runtime_name
}

output "runtime_arn" {
  description = "ARN of the agent runtime, for InvokeAgentRuntime."
  value       = aws_bedrockagentcore_agent_runtime.askwri.agent_runtime_arn
}

output "runtime_id" {
  description = "ID of the agent runtime; its log group is /aws/bedrock-agentcore/runtimes/<id>-DEFAULT."
  value       = aws_bedrockagentcore_agent_runtime.askwri.agent_runtime_id
}
