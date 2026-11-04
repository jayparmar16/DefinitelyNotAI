# askwri-vpc: private subnets only, no internet route and no NAT gateway. AWS services are
# reached through VPC endpoints.

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
  subnets = {
    "askwri-app-a" = { cidr = cidrsubnet(var.vpc_cidr, 8, 1), az = local.azs[0], tier = "app" }
    "askwri-app-b" = { cidr = cidrsubnet(var.vpc_cidr, 8, 2), az = local.azs[1], tier = "app" }
    "askwri-db-a"  = { cidr = cidrsubnet(var.vpc_cidr, 8, 11), az = local.azs[0], tier = "db" }
    "askwri-db-b"  = { cidr = cidrsubnet(var.vpc_cidr, 8, 12), az = local.azs[1], tier = "db" }
  }
  interface_endpoints = ["bedrock-runtime", "bedrock-agent-runtime", "secretsmanager", "logs"]
  app_subnet_ids      = [for name, s in aws_subnet.private : s.id if local.subnets[name].tier == "app"]
}

resource "aws_vpc" "askwri" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = "askwri-vpc" }
}

resource "aws_subnet" "private" {
  for_each          = local.subnets
  vpc_id            = aws_vpc.askwri.id
  cidr_block        = each.value.cidr
  availability_zone = each.value.az
  tags              = { Name = each.key }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.askwri.id
  tags   = { Name = "askwri-rt-private" }
}

resource "aws_route_table_association" "private" {
  for_each       = aws_subnet.private
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private.id
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.askwri.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
  tags              = { Name = "askwri-vpce-s3" }
}

resource "aws_vpc_endpoint" "interface" {
  for_each            = toset(local.interface_endpoints)
  vpc_id              = aws_vpc.askwri.id
  service_name        = "com.amazonaws.${var.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = local.app_subnet_ids
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true
  tags                = { Name = "askwri-vpce-${each.key}" }
}

# Security groups. Rules are separate resources; a group with no egress rule allows none.

resource "aws_security_group" "lambda" {
  name        = "askwri-sg-lambda"
  description = "Ingestion and tool Lambdas"
  vpc_id      = aws_vpc.askwri.id
  tags        = { Name = "askwri-sg-lambda" }
}

resource "aws_security_group" "db" {
  name        = "askwri-sg-db"
  description = "Aurora cluster askwri-db"
  vpc_id      = aws_vpc.askwri.id
  tags        = { Name = "askwri-sg-db" }
}

resource "aws_security_group" "endpoints" {
  name        = "askwri-sg-endpoints"
  description = "Interface VPC endpoints"
  vpc_id      = aws_vpc.askwri.id
  tags        = { Name = "askwri-sg-endpoints" }
}

resource "aws_vpc_security_group_egress_rule" "lambda_to_db" {
  security_group_id            = aws_security_group.lambda.id
  referenced_security_group_id = aws_security_group.db.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "PostgreSQL to Aurora"
}

resource "aws_vpc_security_group_egress_rule" "lambda_to_endpoints" {
  security_group_id            = aws_security_group.lambda.id
  referenced_security_group_id = aws_security_group.endpoints.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "HTTPS to interface endpoints"
}

resource "aws_vpc_security_group_egress_rule" "lambda_to_s3" {
  security_group_id = aws_security_group.lambda.id
  prefix_list_id    = aws_vpc_endpoint.s3.prefix_list_id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "HTTPS to S3 through the gateway endpoint"
}

resource "aws_vpc_security_group_ingress_rule" "db_from_lambda" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.lambda.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "PostgreSQL from the Lambdas"
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_from_lambda" {
  security_group_id            = aws_security_group.endpoints.id
  referenced_security_group_id = aws_security_group.lambda.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "HTTPS from the Lambdas"
}
