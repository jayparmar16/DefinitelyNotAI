# askwri-db: Aurora PostgreSQL Serverless v2 with pgvector, private, with the Data API on.
# The master password is write-only: it is never stored in Terraform state or outputs.
# It lives only in the askwri/db secret, which the Data API uses to apply db/schema.sql.

ephemeral "random_password" "master" {
  length  = 32
  special = false
}

locals {
  # Bump to rotate the master password (writes a new one to the cluster and the secret).
  master_password_version = 1
}

resource "aws_db_subnet_group" "askwri" {
  name       = "askwri-db-subnets"
  subnet_ids = var.subnet_ids
}

resource "aws_rds_cluster" "askwri" {
  cluster_identifier                  = "askwri-db"
  engine                              = "aurora-postgresql"
  engine_mode                         = "provisioned"
  engine_version                      = "18.6"
  database_name                       = "askwri"
  master_username                     = "askwri_admin"
  master_password_wo                  = ephemeral.random_password.master.result
  master_password_wo_version          = local.master_password_version
  db_subnet_group_name                = aws_db_subnet_group.askwri.name
  vpc_security_group_ids              = [var.security_group_id]
  storage_encrypted                   = true
  enable_http_endpoint                = true
  iam_database_authentication_enabled = true
  backup_retention_period             = 1
  # shortcut: no final snapshot and no deletion protection - hackathon sandbox, torn down after
  skip_final_snapshot = true

  serverlessv2_scaling_configuration {
    min_capacity             = var.min_capacity
    max_capacity             = var.max_capacity
    seconds_until_auto_pause = var.min_capacity == 0 ? var.seconds_until_auto_pause : null
  }
}

resource "aws_rds_cluster_instance" "writer" {
  identifier          = "askwri-db-1"
  cluster_identifier  = aws_rds_cluster.askwri.id
  instance_class      = "db.serverless"
  engine              = aws_rds_cluster.askwri.engine
  engine_version      = aws_rds_cluster.askwri.engine_version
  publicly_accessible = false
}

resource "aws_secretsmanager_secret" "db" {
  name        = "askwri/db"
  description = "Master credentials for askwri-db, used by the Data API to apply the schema."
  # shortcut: delete immediately on destroy - a 7-30 day recovery window blocks re-creating
  # the same name in a re-deployed sandbox
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string_wo = jsonencode({
    engine   = "postgres"
    username = aws_rds_cluster.askwri.master_username
    password = ephemeral.random_password.master.result
    host     = aws_rds_cluster.askwri.endpoint
    port     = aws_rds_cluster.askwri.port
    dbname   = aws_rds_cluster.askwri.database_name
  })
  secret_string_wo_version = local.master_password_version
}
