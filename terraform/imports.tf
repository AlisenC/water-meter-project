# One-time adoption of the resources that were created by hand before this
# configuration existed. After the first successful apply, delete this file
# and the adopt_ids variable: these blocks would fail on a fresh account
# (e.g. an AWS account migration) where none of these resources exist yet.

import {
  to = aws_db_instance.main
  id = var.db_identifier
}

import {
  to = aws_security_group.db
  id = var.adopt_ids.security_group_id
}

import {
  to = aws_vpc_security_group_ingress_rule.db_from_home
  id = var.adopt_ids.db_ingress_rule_id
}

import {
  to = cloudflare_zero_trust_tunnel_cloudflared.water_meter
  id = "${var.cloudflare_account_id}/${var.adopt_ids.tunnel_id}"
}

import {
  to = cloudflare_dns_record.water_meter
  id = "${var.cloudflare_zone_id}/${var.adopt_ids.dns_record_id}"
}
