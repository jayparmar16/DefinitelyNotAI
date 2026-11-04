output "db_subnet_ids" {
  description = "askwri-db-a and askwri-db-b, for Aurora."
  value       = [for name, s in aws_subnet.private : s.id if local.subnets[name].tier == "db"]
}

output "db_security_group_id" {
  description = "askwri-sg-db."
  value       = aws_security_group.db.id
}

output "app_subnet_ids" {
  description = "askwri-app-a and askwri-app-b, for the Lambdas."
  value       = local.app_subnet_ids
}

output "lambda_security_group_id" {
  description = "askwri-sg-lambda."
  value       = aws_security_group.lambda.id
}
