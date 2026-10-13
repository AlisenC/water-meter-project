# The tunnel is locally managed: its ingress rules live in the
# cloudflared-config ConfigMap (charts/water-meter), and its credentials are
# the cloudflared-credentials SealedSecret. Terraform only owns the tunnel's
# existence and the DNS record pointing at it.
resource "cloudflare_zero_trust_tunnel_cloudflared" "water_meter" {
  account_id = var.cloudflare_account_id
  name       = var.tunnel_name
  config_src = "local"

  lifecycle {
    # Recreating the tunnel changes its ID and invalidates the sealed
    # credentials the cluster runs with.
    prevent_destroy = true
  }
}

resource "cloudflare_dns_record" "water_meter" {
  zone_id = var.cloudflare_zone_id
  name    = var.public_hostname
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.water_meter.id}.cfargotunnel.com"
  proxied = true
  ttl     = 1 # "automatic" -- required for proxied records
}
