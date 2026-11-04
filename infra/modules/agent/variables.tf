variable "region" {
  description = "Region, used in ARNs."
  type        = string
}

variable "account_id" {
  description = "Team account ID, used in names and ARNs."
  type        = string
}

variable "package_path" {
  description = "Path of build/agent.zip (infra/build/agent.sh)."
  type        = string
}

variable "gateway_url" {
  description = "MCP endpoint of askwri-gateway."
  type        = string
}

variable "gateway_secret_name" {
  description = "Secret with the gateway's client credentials (askwri/gateway-client)."
  type        = string
}

variable "gateway_secret_arn" {
  description = "ARN of that secret, for the role's permission."
  type        = string
}

variable "small_model_id" {
  description = "Small model or inference profile: planning, rewrites, claim checks."
  type        = string
}

variable "large_model_id" {
  description = "Large model or inference profile: the final answer."
  type        = string
}

variable "relevance_threshold" {
  description = "Best rerank score at or above which evidence counts as strong enough to answer."
  type        = number
}

variable "quick_max_rounds" {
  description = "Search rounds per question in Quick answer."
  type        = number
}

variable "deep_max_rounds" {
  description = "Search rounds per sub-question in Deep research."
  type        = number
}

variable "grounding_threshold" {
  description = "Guardrails contextual grounding threshold (0-0.99): higher blocks more."
  type        = number
}

variable "relevance_grounding_threshold" {
  description = "Guardrails relevance threshold (0-0.99): is the answer relevant to the question."
  type        = number
}
