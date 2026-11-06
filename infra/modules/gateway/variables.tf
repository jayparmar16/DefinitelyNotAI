variable "region" {
  description = "Region, used in the Cognito discovery and token URLs."
  type        = string
}

variable "account_id" {
  description = "Team account ID: makes the Cognito domain unique and scopes the gateway role's trust."
  type        = string
}

variable "tool_function_arns" {
  description = "Tool Lambda name (search, passage, coverage, authors, translate) -> ARN."
  type        = map(string)
}
