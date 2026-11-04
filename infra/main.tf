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

module "tools" {
  source                 = "./modules/tools"
  region                 = var.region
  account_id             = var.team_account_id
  package_path           = "${path.root}/../build/tools.zip"
  subnet_ids             = module.network.app_subnet_ids
  security_group_id      = module.network.lambda_security_group_id
  db_host                = module.database.endpoint
  db_name                = module.database.database_name
  db_cluster_resource_id = module.database.cluster_resource_id
  embedding_model_id     = var.embedding_model_id
  rerank_model_id        = var.rerank_model_id
  translate_model_id     = var.small_model_id
}

module "gateway" {
  source             = "./modules/gateway"
  region             = var.region
  account_id         = var.team_account_id
  tool_function_arns = module.tools.function_arns
}

module "agent" {
  source                        = "./modules/agent"
  region                        = var.region
  account_id                    = var.team_account_id
  package_path                  = "${path.root}/../build/agent.zip"
  gateway_url                   = module.gateway.gateway_url
  gateway_secret_name           = module.gateway.gateway_client_secret_name
  gateway_secret_arn            = module.gateway.gateway_client_secret_arn
  small_model_id                = var.small_model_id
  large_model_id                = var.large_model_id
  relevance_threshold           = var.relevance_threshold
  quick_max_rounds              = var.quick_max_rounds
  deep_max_rounds               = var.deep_max_rounds
  grounding_threshold           = var.grounding_threshold
  relevance_grounding_threshold = var.relevance_grounding_threshold
}
