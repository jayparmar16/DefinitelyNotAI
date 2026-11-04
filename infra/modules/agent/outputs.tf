output "runtime_name" {
  description = "Name of the agent runtime."
  value       = aws_bedrockagentcore_agent_runtime.askwri.agent_runtime_name
}

output "runtime_arn" {
  description = "ARN of the agent runtime, for InvokeAgentRuntime."
  value       = aws_bedrockagentcore_agent_runtime.askwri.agent_runtime_arn
}
