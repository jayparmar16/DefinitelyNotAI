output "url" {
  description = "Public URL of askwri-api (the UI's NEXT_PUBLIC_ASKWRI_API_URL)."
  value       = aws_lambda_function_url.api.function_url
}

output "api_key_secret_name" {
  description = "Secret holding the X-AskWRI-Key value."
  value       = aws_secretsmanager_secret.api_key.name
}
