# askwri-users: who may use the hosted UI. Invite-only (no self sign-up); people sign in on
# Cognito's managed login page and the UI sends their access token to askwri-api.

resource "aws_cognito_user_pool" "users" {
  name                     = "askwri-users"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "OPTIONAL"
  deletion_protection      = "ACTIVE"

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  software_token_mfa_configuration {
    enabled = true
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = false
    temporary_password_validity_days = 7
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}

resource "aws_cognito_user_group" "admins" {
  name         = "askwri-admins"
  user_pool_id = aws_cognito_user_pool.users.id
  description  = "May open the admin page (/admin/)."
}

# A random prefix: the domain is public (it is in the UI bundle) and must not carry the account ID.
resource "random_id" "domain" {
  byte_length = 4
}

resource "aws_cognito_user_pool_domain" "login" {
  domain                = "askwri-${random_id.domain.hex}"
  user_pool_id          = aws_cognito_user_pool.users.id
  managed_login_version = 2
}

resource "aws_cognito_user_pool_client" "ui" {
  name         = "askwri-ui"
  user_pool_id = aws_cognito_user_pool.users.id

  # A browser app: no client secret, authorization code with PKCE.
  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "aws.cognito.signin.user.admin"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = [for origin in var.origins : "${origin}/"]
  logout_urls                          = [for origin in var.origins : "${origin}/"]
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_SRP_AUTH"]
  prevent_user_existence_errors        = "ENABLED"
  enable_token_revocation              = true

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 12
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "hours"
  }
}

resource "aws_cognito_managed_login_branding" "ui" {
  user_pool_id                = aws_cognito_user_pool.users.id
  client_id                   = aws_cognito_user_pool_client.ui.id
  use_cognito_provided_values = true
}

data "aws_region" "current" {}
