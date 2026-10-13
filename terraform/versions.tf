terraform {
  # 1.11+ for S3-native state locking (use_lockfile) and write-only
  # attributes (the RDS master password never lands in state).
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }

  # Partial config: bucket/region live in the gitignored backend.hcl (see
  # backend.hcl.example) since the bucket name embeds the AWS account ID.
  # Init with: terraform init -backend-config=backend.hcl
  backend "s3" {
    key          = "water-meter/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
