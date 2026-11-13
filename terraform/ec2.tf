# The single server: Jenkins + Docker, running the dashboard and demo-app.
# user_data.sh installs everything on first boot (takes about 5 minutes).

resource "aws_instance" "main" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.instance_type
  key_name               = var.key_name
  vpc_security_group_ids = [aws_security_group.main.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name
  monitoring             = var.detailed_monitoring

  user_data = templatefile("${path.module}/user_data.sh", {
    aws_region              = var.aws_region
    ecr_repository_url      = aws_ecr_repository.demo_app.repository_url
    sns_topic_arn           = aws_sns_topic.alerts.arn
    demo_app_log_group      = aws_cloudwatch_log_group.demo_app.name
    metrics_namespace       = local.metrics_namespace
    trivy_version           = var.trivy_version
    docker_compose_version  = var.docker_compose_version
    docker_buildx_version   = var.docker_buildx_version
    cloudwatch_agent_config = file("${path.module}/../monitoring/cloudwatch-agent.json")
  })

  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_size
    encrypted   = true
  }

  # Require IMDSv2 (session tokens) for the instance metadata service.
  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  tags = {
    Name = "${var.project_name}-server"
  }

  lifecycle {
    # A newer Amazon Linux image must not replace a running server on the next apply.
    ignore_changes = [ami]
  }
}

# Fixed public IP. It survives stop/start, so the Jenkins URL, the GitHub
# webhook and your bookmarks keep working when the instance is stopped overnight.
resource "aws_eip" "main" {
  instance = aws_instance.main.id
  domain   = "vpc"

  tags = {
    Name = "${var.project_name}-eip"
  }
}
