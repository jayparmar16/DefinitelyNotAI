data "aws_caller_identity" "current" {}

# The role Terraform runs as (WSParticipantRole), not the temporary session.
data "aws_iam_session_context" "deployer" {
  arn = data.aws_caller_identity.current.arn
}

module "network" {
  source   = "./modules/network"
  region   = var.region
  vpc_cidr = var.vpc_cidr
}

module "storage" {
  source       = "./modules/storage"
  account_id   = var.team_account_id
  deployer_arn = data.aws_iam_session_context.deployer.issuer_arn
}

module "database" {
  source                   = "./modules/database"
  subnet_ids               = module.network.db_subnet_ids
  security_group_id        = module.network.db_security_group_id
  min_capacity             = var.db_min_capacity
  max_capacity             = var.db_max_capacity
  seconds_until_auto_pause = var.db_seconds_until_auto_pause
}

resource "aws_resourcegroups_group" "askwri" {
  name        = "askwri-rg"
  description = "Every AskWRI resource found by the Project tag."

  resource_query {
    query = jsonencode({
      ResourceTypeFilters = ["AWS::AllSupported"]
      TagFilters          = [{ Key = "Project", Values = ["AskWRI"] }]
    })
  }
}
