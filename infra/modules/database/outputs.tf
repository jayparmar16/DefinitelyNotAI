output "cluster_identifier" {
  description = "askwri-db."
  value       = aws_rds_cluster.askwri.cluster_identifier
}

output "endpoint" {
  description = "Writer endpoint host name, reachable only from askwri-sg-lambda."
  value       = aws_rds_cluster.askwri.endpoint
}

output "cluster_resource_id" {
  description = "Cluster resource ID, used in rds-db:connect IAM policies."
  value       = aws_rds_cluster.askwri.cluster_resource_id
}

output "database_name" {
  description = "askwri."
  value       = aws_rds_cluster.askwri.database_name
}
