output "bucket" {
  description = "Bucket holding the UI's static files."
  value       = aws_s3_bucket.web.bucket
}

output "distribution_id" {
  description = "CloudFront distribution to invalidate after an upload."
  value       = aws_cloudfront_distribution.web.id
}

output "origin" {
  description = "The UI's https origin, for CORS."
  value       = "https://${aws_cloudfront_distribution.web.domain_name}"
}
