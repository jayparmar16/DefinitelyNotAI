output "corpus_bucket" {
  description = "Bucket for raw PDFs (raw/), extracted text (text/) and evaluation files (eval/)."
  value       = module.storage.corpus_bucket
}

output "db_cluster_identifier" {
  description = "Aurora cluster name, for the Data API and the console."
  value       = module.database.cluster_identifier
}

output "gateway_url" {
  description = "MCP endpoint of askwri-gateway (needs a Cognito token: see gateway_client_secret)."
  value       = module.gateway.gateway_url
}

output "gateway_client_secret" {
  description = "Secrets Manager secret holding the gateway's client credentials and token URL."
  value       = module.gateway.gateway_client_secret_name
}

output "agent_runtime_name" {
  description = "AgentCore Runtime agent: ask it with `uv run python -m askwri.agent.ask \"question\"`."
  value       = module.agent.runtime_name
}

output "api_url" {
  description = "askwri-api URL for the UI (NEXT_PUBLIC_ASKWRI_API_URL)."
  value       = module.api.url
}

output "api_key_secret" {
  description = "Secret holding the key the UI sends as X-AskWRI-Key."
  value       = module.api.api_key_secret_name
}
