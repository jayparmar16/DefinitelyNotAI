variable "region" {
  description = "Region, used in ARNs."
  type        = string
}

variable "account_id" {
  description = "Team account ID, used in ARNs."
  type        = string
}

variable "package_path" {
  description = "Path of build/tools.zip (infra/build/tools.sh)."
  type        = string
}

variable "subnet_ids" {
  description = "askwri-app-a and askwri-app-b."
  type        = list(string)
}

variable "security_group_id" {
  description = "askwri-sg-lambda."
  type        = string
}

variable "db_host" {
  description = "askwri-db writer endpoint."
  type        = string
}

variable "db_name" {
  description = "Database name."
  type        = string
}

variable "db_cluster_resource_id" {
  description = "askwri-db cluster resource ID, for rds-db:connect."
  type        = string
}

variable "embedding_model_id" {
  description = "Bedrock embedding model ID."
  type        = string
}

variable "rerank_model_id" {
  description = "Bedrock rerank model ID."
  type        = string
}

variable "translate_model_id" {
  description = "Bedrock model or global inference profile ID used for translation."
  type        = string
}
