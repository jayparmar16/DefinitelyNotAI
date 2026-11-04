terraform {
  # 1.10+ for S3-native state locking (use_lockfile); 1.11+ for write-only arguments.
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.71"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }

  # Settings come from backend.hcl, written by bootstrap/create-state-bucket.sh.
  backend "s3" {}
}
