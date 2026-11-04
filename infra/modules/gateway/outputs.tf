output "gateway_url" {
  description = "MCP endpoint of askwri-gateway."
  value       = aws_bedrockagentcore_gateway.askwri.gateway_url
}

output "gateway_client_secret_name" {
  description = "Secrets Manager secret with the client ID, client secret, token URL and scope."
  value       = aws_secretsmanager_secret.gateway_client.name
}
