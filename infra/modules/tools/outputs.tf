output "function_arns" {
  description = "Tool name -> Lambda ARN, for the gateway targets."
  value       = { for name, fn in aws_lambda_function.tool : name => fn.arn }
}
