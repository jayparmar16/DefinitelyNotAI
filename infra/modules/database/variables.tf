variable "subnet_ids" {
  description = "askwri-db-a and askwri-db-b."
  type        = list(string)
}

variable "security_group_id" {
  description = "askwri-sg-db."
  type        = string
}

variable "min_capacity" {
  description = "Minimum ACUs; 0 lets the cluster pause when idle."
  type        = number
}

variable "max_capacity" {
  description = "Maximum ACUs."
  type        = number
}

variable "seconds_until_auto_pause" {
  description = "Idle seconds before pausing (only when min_capacity is 0)."
  type        = number
}
