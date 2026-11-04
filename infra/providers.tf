provider "aws" {
  region = var.region
  # Only the team sandbox is a deployment target; teammates' sandboxes are refused.
  allowed_account_ids = [var.team_account_id]

  default_tags {
    tags = {
      Project     = "AskWRI"
      Environment = "hackathon"
      Team        = var.team
      Owner       = var.owner
      ManagedBy   = "terraform"
    }
  }
}
