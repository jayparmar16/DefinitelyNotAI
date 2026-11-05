output "user_pool_id" {
  description = "askwri-users pool, for adding people (aws cognito-idp admin-create-user)."
  value       = aws_cognito_user_pool.users.id
}

output "client_id" {
  description = "The UI's app client (public: it is in the UI bundle)."
  value       = aws_cognito_user_pool_client.ui.id
}

output "login_domain" {
  description = "Managed login domain the UI sends people to."
  value       = "https://${aws_cognito_user_pool_domain.login.domain}.auth.${data.aws_region.current.region}.amazoncognito.com"
}
