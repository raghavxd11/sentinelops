# Firewall for the instance.
#   22    SSH        your IP only
#   8080  Jenkins    your IP + GitHub webhook ranges
#   5000  dashboard, 8000 demo-app production, 8001 demo-app staging: open for the demo
# Everything else inbound is blocked. All outbound traffic is allowed
# (package installs, ECR, CloudWatch, GitHub).

locals {
  jenkins_cidrs = concat(
    [var.my_ip_cidr],
    var.enable_github_webhook ? var.github_webhook_cidrs : [],
  )

  app_ports = {
    5000 = "SentinelOps dashboard"
    8000 = "demo-app production"
    8001 = "demo-app staging"
  }
}

resource "aws_security_group" "main" {
  name        = "${var.project_name}-sg"
  description = "SentinelOps: SSH and Jenkins restricted, app ports open"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH from my IP"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.my_ip_cidr]
  }

  ingress {
    description = "Jenkins from my IP and GitHub webhooks"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = local.jenkins_cidrs
  }

  dynamic "ingress" {
    for_each = local.app_ports
    content {
      description = ingress.value
      from_port   = ingress.key
      to_port     = ingress.key
      protocol    = "tcp"
      cidr_blocks = var.app_ports_cidrs
    }
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-sg"
  }
}
