variable "region" {
  description = "Region, used in the VPC endpoint service names."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block of askwri-vpc."
  type        = string
}
