# The repo is public: anything identifying (home IP, account IDs, email)
# comes from the gitignored terraform.tfvars, never from defaults here.

variable "aws_region" {
  description = "AWS region the RDS instance and state bucket live in."
  type        = string
  default     = "us-west-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to authenticate with (null = default credential chain)."
  type        = string
  default     = null
}

variable "state_bucket_name" {
  description = "Globally unique name of the S3 bucket holding Terraform state. Must match backend.hcl."
  type        = string
}

variable "home_ip_cidr" {
  description = "The home network's public IP as a /32 -- the only source allowed to reach Postgres."
  type        = string
  sensitive   = true
}

variable "db_identifier" {
  description = "RDS instance identifier."
  type        = string
  default     = "water-meter-db"
}

variable "db_name" {
  description = "Initial database name created on the instance."
  type        = string
  default     = "water_meter"
}

variable "db_username" {
  description = "RDS master username."
  type        = string
}

variable "db_password" {
  description = <<-EOT
    RDS master password. Only needed when *creating* the instance (e.g. an
    account migration); leave unset when managing the existing one. Sent as a
    write-only attribute, so it is never stored in state. Pass via the
    TF_VAR_db_password environment variable rather than terraform.tfvars.
  EOT
  type        = string
  default     = null
  sensitive   = true
  ephemeral   = true
}

variable "db_password_version" {
  description = "Set (e.g. 1) together with db_password to send it; increment to rotate. Leave null otherwise."
  type        = number
  default     = null
}

variable "db_security_group_name" {
  description = "Name of the security group attached to the RDS instance (changing it forces replacement)."
  type        = string
}

variable "db_security_group_description" {
  description = "Description of that security group (changing it forces replacement)."
  type        = string
}

variable "budget_email" {
  description = "Email address that receives AWS Budgets cost alerts."
  type        = string
}

variable "budget_limit_usd" {
  description = "Monthly cost (after credits) above which an alert is emailed."
  type        = string
  default     = "1.0"
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID that owns the tunnel."
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID of the public hostname's domain."
  type        = string
}

variable "tunnel_name" {
  description = "Name of the cloudflared tunnel (changing it forces replacement)."
  type        = string
  default     = "water-meter"
}

variable "public_hostname" {
  description = "Public hostname served through the tunnel. Must match cloudflared.hostname in apps/water-meter/release.yaml."
  type        = string
  default     = "water-meter.steamingcloud.com"
}

variable "adopt_ids" {
  description = <<-EOT
    IDs of the hand-created resources, used only by the one-time import
    blocks in imports.tf. Remove this variable together with imports.tf once
    the first apply has adopted everything.
  EOT
  type = object({
    security_group_id  = string
    db_ingress_rule_id = string
    tunnel_id          = string
    dns_record_id      = string
  })
  default = null
}
