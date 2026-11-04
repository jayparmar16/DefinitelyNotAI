variable "team_account_id" {
  description = "The team sandbox account ID. Set TF_VAR_team_account_id; never commit it."
  type        = string

  # An empty value (for example from an expired session) would rename the corpus bucket
  # and plan its replacement, so refuse it outright.
  validation {
    condition     = can(regex("^[0-9]{12}$", var.team_account_id))
    error_message = "team_account_id must be the 12-digit team account ID."
  }
}

variable "region" {
  description = "Region for every resource."
  type        = string
  default     = "us-west-2"
}

variable "team" {
  description = "Value of the Team tag."
  type        = string
}

variable "owner" {
  description = "Value of the Owner tag (an email address)."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block of askwri-vpc; subnets are carved from it."
  type        = string
  default     = "10.20.0.0/16"
}

variable "db_min_capacity" {
  description = "Aurora minimum ACUs. 0 pauses when idle (resume takes 15 s or more); 0.5 for demos."
  type        = number
  default     = 0
}

variable "db_max_capacity" {
  description = "Aurora maximum ACUs."
  type        = number
  default     = 4
}

variable "db_seconds_until_auto_pause" {
  description = "Idle seconds before Aurora pauses; only applies when db_min_capacity is 0."
  type        = number
  default     = 3600
}

# Model IDs live here, not in code. Claude models in us-west-2 run only through inference
# profiles; the embedding and rerank models run in-region.
variable "embedding_model_id" {
  description = "Query embedding model (a us. inference profile); must match the model askwri.ingest.load embeds passages with, and vector(1024) in db/schema.sql."
  type        = string
  default     = "us.cohere.embed-v4:0"
}

variable "rerank_model_id" {
  description = "Rerank model for search results."
  type        = string
  default     = "amazon.rerank-v1:0"
}

variable "small_model_id" {
  description = "Haiku-class model (inference profile) for translation, planning, rewrites and checks."
  type        = string
  # shortcut: Haiku 4.5 - Claude Haiku 5.5 is blocked in the team sandbox (needs an AWS
  # Marketplace subscription the sandbox role can't make). Switch back when it is enabled.
  default = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "large_model_id" {
  description = "Sonnet-class model (inference profile) for the final answer and reports."
  type        = string
  default     = "global.anthropic.claude-sonnet-5-5"
}

variable "relevance_threshold" {
  description = "Best rerank score that counts as strong evidence. Measured on the sample: answerable questions scored 0.018+, unanswerable 0.002 or less. Re-tune with the test set."
  type        = number
  default     = 0.01
}

variable "quick_max_rounds" {
  description = "Search rounds per question in Quick answer."
  type        = number
  default     = 2
}

variable "deep_max_rounds" {
  description = "Search rounds per sub-question in Deep research."
  type        = number
  default     = 3
}

variable "grounding_threshold" {
  description = "Bedrock Guardrails contextual grounding threshold for answers (0-0.99)."
  type        = number
  default     = 0.5
}

variable "allowed_origins" {
  description = "Browser origins allowed to call askwri-api. Add the CloudFront domain when the UI is hosted."
  type        = list(string)
  default     = ["http://localhost:3000"]
}

variable "api_max_concurrency" {
  description = "Most API requests served at once (Lambda reserved concurrency)."
  type        = number
  default     = 5
}

variable "web_adapter_layer_arn" {
  description = "AWS Lambda Web Adapter layer for arm64 (published by AWS), for response streaming."
  type        = string
  default     = "arn:aws:lambda:us-west-2:753240598075:layer:LambdaAdapterLayerArm64:25"
}
