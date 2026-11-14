# The server: Jenkins + Docker, running the dashboard and demo-app.

# Find the newest Amazon Linux 2023 image.
data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
}

resource "aws_instance" "server" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.instance_type
  key_name               = var.key_name
  vpc_security_group_ids = [aws_security_group.server.id]
  iam_instance_profile   = "LabInstanceProfile"

  user_data                   = file("${path.module}/user_data.sh")
  user_data_replace_on_change = true

  root_block_device {
    volume_type = "gp3"
    volume_size = 30
  }

  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name = "${var.project_name}-server"
  }

  lifecycle {
    ignore_changes = [ami]
  }
}

# Fixed public IP that survives stop/start.
resource "aws_eip" "server" {
  instance = aws_instance.server.id
  domain   = "vpc"

  tags = {
    Name = "${var.project_name}-eip"
  }
}