output "rds_endpoint" {
  description = "Host for DATABASE_URL (re-seal it with kubeseal if this changes)."
  value       = aws_db_instance.main.address
}

output "tunnel_id" {
  description = "Tunnel ID -- must match cloudflared.tunnelId in apps/water-meter/release.yaml."
  value       = cloudflare_zero_trust_tunnel_cloudflared.water_meter.id
}

output "tunnel_cname" {
  description = "DNS target the public hostname points at."
  value       = cloudflare_dns_record.water_meter.content
}

output "state_bucket" {
  description = "S3 bucket holding this configuration's state."
  value       = aws_s3_bucket.tfstate.bucket
}
