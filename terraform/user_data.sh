#!/bin/bash
# First-boot setup for the SentinelOps server (Amazon Linux 2023), run once as root.
#
# Terraform renders this file with templatefile(): every dollar-brace
# placeholder is filled in by Terraform before the instance sees it. Bash
# variables in this file are therefore written as plain $NAME, without braces.
#
# Progress and errors: /var/log/user-data.log  (sudo tail -f /var/log/user-data.log)

# shellcheck disable=SC2154  # the dollar-brace placeholders are Terraform's, not bash variables
set -euxo pipefail
exec > >(tee -a /var/log/user-data.log) 2>&1

# ---------- 1. packages ----------
# git: Jenkins checkouts | jq: report.sh builds JSON | python3.11: lint + tests
# java 21: Jenkins | fontconfig: needed by Jenkins | amazon-cloudwatch-agent: memory/disk metrics
dnf install -y docker git jq python3.11 python3.11-pip \
  java-21-amazon-corretto-headless fontconfig amazon-cloudwatch-agent

# ---------- 2. Docker ----------
# Rotate local json-file logs so they cannot fill the disk.
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
systemctl enable --now docker

# Compose and Buildx plugins (not packaged for Amazon Linux 2023).
PLUGIN_DIR=/usr/local/lib/docker/cli-plugins
mkdir -p "$PLUGIN_DIR"
curl -fsSL -o "$PLUGIN_DIR/docker-compose" \
  "https://github.com/docker/compose/releases/download/v${docker_compose_version}/docker-compose-linux-x86_64"
curl -fsSL -o "$PLUGIN_DIR/docker-buildx" \
  "https://github.com/docker/buildx/releases/download/v${docker_buildx_version}/buildx-v${docker_buildx_version}.linux-amd64"
chmod +x "$PLUGIN_DIR/docker-compose" "$PLUGIN_DIR/docker-buildx"

usermod -aG docker ec2-user

# ---------- 3. Trivy ----------
dnf install -y "https://github.com/aquasecurity/trivy/releases/download/v${trivy_version}/trivy_${trivy_version}_Linux-64bit.rpm"

# ---------- 4. settings shared by Jenkins and SSH sessions ----------
# Values come from Terraform, so nothing has to be typed into Jenkins by hand.
cat > /etc/sentinelops.env <<'EOF'
AWS_REGION=${aws_region}
AWS_DEFAULT_REGION=${aws_region}
ECR_REPOSITORY_URL=${ecr_repository_url}
SNS_TOPIC_ARN=${sns_topic_arn}
DEMO_APP_LOG_GROUP=${demo_app_log_group}
DASHBOARD_URL=http://localhost:5000
EOF
chmod 644 /etc/sentinelops.env

# Login shells (ssh ec2-user@...) get the same variables, for running scripts/ by hand.
cat > /etc/profile.d/sentinelops.sh <<'EOF'
set -a
. /etc/sentinelops.env
set +a
EOF

# ---------- 5. Jenkins ----------
curl -fsSL -o /etc/yum.repos.d/jenkins.repo https://pkg.jenkins.io/redhat-stable/jenkins.repo
dnf install -y jenkins
usermod -aG docker jenkins   # Jenkins builds and runs containers

# Every pipeline run inherits these environment variables from the Jenkins service.
mkdir -p /etc/systemd/system/jenkins.service.d
cat > /etc/systemd/system/jenkins.service.d/sentinelops.conf <<'EOF'
[Service]
EnvironmentFile=/etc/sentinelops.env
EOF
systemctl daemon-reload
systemctl enable --now jenkins

# ---------- 6. CloudWatch agent (memory + disk metrics) ----------
# The config is monitoring/cloudwatch-agent.json from the repository.
CW_CONFIG=/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
cat > "$CW_CONFIG" <<'EOF'
${cloudwatch_agent_config}
EOF
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 -s -c "file:$CW_CONFIG"

# ---------- 7. demo-app health probe ----------
# Every minute: if the production container exists, publish DemoAppHealthy = 1
# (GET /health returns 200) or 0 to CloudWatch. The demo-app-unhealthy alarm
# watches this metric.
cat > /usr/local/bin/sentinelops-health-probe <<'EOF'
#!/bin/bash
set -u
docker inspect demo-app-prod > /dev/null 2>&1 || exit 0
if curl -fsS -m 5 -o /dev/null http://localhost:8000/health; then value=1; else value=0; fi
aws cloudwatch put-metric-data --region "$AWS_REGION" --namespace "${metrics_namespace}" \
  --metric-name DemoAppHealthy --dimensions Environment=production --value "$value"
EOF
chmod 755 /usr/local/bin/sentinelops-health-probe

cat > /etc/systemd/system/sentinelops-health-probe.service <<'EOF'
[Unit]
Description=Publish demo-app production health to CloudWatch
After=docker.service

[Service]
Type=oneshot
EnvironmentFile=/etc/sentinelops.env
ExecStart=/usr/local/bin/sentinelops-health-probe
EOF

cat > /etc/systemd/system/sentinelops-health-probe.timer <<'EOF'
[Unit]
Description=Run the demo-app health probe every minute

[Timer]
OnBootSec=2min
OnUnitActiveSec=1min
AccuracySec=5s

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now sentinelops-health-probe.timer

echo "SentinelOps bootstrap finished"
