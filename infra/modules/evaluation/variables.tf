variable "region" {
  description = "AWS region."
  type        = string
}

variable "account_id" {
  description = "Team AWS account ID."
  type        = string
}

variable "agent_runtime_id" {
  description = "ID of askwri_agent, whose runtime log group the judges read."
  type        = string
}

variable "agent_service_name" {
  description = "service.name on the agent's spans."
  type        = string
  default     = "askwri_agent.DEFAULT"
}

variable "online_eval_sampling_percentage" {
  description = "Share of live sessions AgentCore judges (0-100). Each judged session costs judge-model tokens."
  type        = number
}
