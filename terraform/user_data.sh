#!/bin/bash
# First-boot setup for the SentinelOps server (Amazon Linux 2023).
# AWS runs this once, as root. Log: /var/log/user-data.log
set -euxo pipefail
exec > >(tee -a /var/log/user-data.log) 2>&1

# 1. Packages: Docker, git, Java (for Jenkins), Python (for tests)
dnf install -y docker git jq python3.11 python3.11-pip \
  java-21-amazon-corretto-headless fontconfig

# 2. Docker
systemctl enable --now docker
usermod -aG docker ec2-user

# Docker Compose and Buildx plugins
PLUGIN_DIR=/usr/local/lib/docker/cli-plugins
mkdir -p "$PLUGIN_DIR"
curl -fsSL -o "$PLUGIN_DIR/docker-compose" \
  "https://github.com/docker/compose/releases/download/v5.7.1/docker-compose-linux-x86_64"
curl -fsSL -o "$PLUGIN_DIR/docker-buildx" \
  "https://github.com/docker/buildx/releases/download/v0.39.0/buildx-v0.39.0.linux-amd64"
chmod +x "$PLUGIN_DIR/docker-compose" "$PLUGIN_DIR/docker-buildx"

# 3. Trivy (image scanner)
dnf install -y "https://github.com/aquasecurity/trivy/releases/download/v0.76.2/trivy_0.76.2_Linux-64bit.rpm"

# 4. Jenkins
curl -fsSL -o /etc/yum.repos.d/jenkins.repo https://pkg.jenkins.io/redhat-stable/jenkins.repo
dnf install -y jenkins
usermod -aG docker jenkins
systemctl enable --now jenkins

echo "SentinelOps setup finished"