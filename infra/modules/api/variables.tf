variable "package_path" {
  description = "Path of build/api.zip (infra/build/api.sh)."
  type        = string
}

variable "runtime_arn" {
  description = "ARN of the askwri_agent runtime."
  type        = string
}

variable "corpus_bucket" {
  description = "Corpus bucket name; download links are for its raw/ PDFs."
  type        = string
}

variable "allowed_origins" {
  description = "Browser origins allowed to call the API (CORS)."
  type        = list(string)
}

variable "max_concurrency" {
  description = "Most requests served at once (reserved concurrency)."
  type        = number
}

variable "web_adapter_layer_arn" {
  description = "AWS Lambda Web Adapter layer (arm64), which enables response streaming for Python."
  type        = string
}
