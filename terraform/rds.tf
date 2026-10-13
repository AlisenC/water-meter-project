data "aws_vpc" "default" {
  default = true
}

resource "aws_security_group" "db" {
  name        = var.db_security_group_name
  description = var.db_security_group_description
  vpc_id      = data.aws_vpc.default.id

  # Rules are managed as separate resources below; no inline ingress/egress
  # blocks, so Terraform leaves any other existing rules alone.
}

# The k3s cluster reaches RDS from the home network's public IP, so that IP
# is the only allowed source. Update home_ip_cidr if the ISP changes it.
resource "aws_vpc_security_group_ingress_rule" "db_from_home" {
  security_group_id = aws_security_group.db.id
  ip_protocol       = "tcp"
  from_port         = 5432
  to_port           = 5432
  cidr_ipv4         = var.home_ip_cidr
}

resource "aws_db_instance" "main" {
  identifier = var.db_identifier

  engine         = "postgres"
  engine_version = "18.6" # version at adoption; see ignore_changes below

  # No db_name: the instance was created without an initial database (the
  # app's database was created afterwards), and setting one forces
  # replacement.
  username = var.db_username
  # Write-only: never stored in state. Both stay null for the adopted
  # instance, so its existing password is left alone; set both to create the
  # instance, and bump the version to rotate.
  password_wo         = var.db_password
  password_wo_version = var.db_password_version

  # Cost guardrails -- each of these is an option that silently adds to the
  # bill if flipped in the console, so keep them explicit.
  instance_class          = "db.t4g.micro"
  allocated_storage       = 20 # AWS minimum for Postgres
  max_allocated_storage   = 0  # storage autoscaling off: it would grow past the free 20GB
  storage_type            = "gp2"
  multi_az                = false
  backup_retention_period = 1 # backup storage up to the DB's size is free
  monitoring_interval     = 0 # Enhanced Monitoring off (bills CloudWatch)

  # 7-day retention and "standard" Database Insights are free; longer
  # retention and "advanced" mode are not.
  performance_insights_enabled          = true
  performance_insights_retention_period = 7
  database_insights_mode                = "standard"

  storage_encrypted     = true # changing this forces replacement
  copy_tags_to_snapshot = true

  publicly_accessible    = true
  vpc_security_group_ids = [aws_security_group.db.id]

  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.db_identifier}-final"

  lifecycle {
    prevent_destroy = true
    # auto_minor_version_upgrade (on by default) lets RDS move to newer minor
    # versions on its own; without this, Terraform would see each one as
    # drift and try to downgrade. For a deliberate major upgrade, remove this
    # temporarily and set engine_version.
    ignore_changes = [engine_version]
  }
}
