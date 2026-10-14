provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project   = "water-meter"
      ManagedBy = "terraform"
    }
  }
}

# Authenticates via the CLOUDFLARE_API_TOKEN environment variable.
provider "cloudflare" {}
