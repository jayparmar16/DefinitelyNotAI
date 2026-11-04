variable "account_id" {
  description = "Team account ID, used in the bucket name and role ARNs."
  type        = string
}

variable "deployer_arn" {
  description = "ARN of the role that runs Terraform and uploads PDFs (WSParticipantRole)."
  type        = string
}
