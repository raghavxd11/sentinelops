# Alerting and observability: SNS email topic, log groups for container logs,
# CloudWatch alarms (CPU, status checks with auto-recovery, demo-app health)
# and a CloudWatch dashboard.

locals {
  # Namespace for custom metrics (CloudWatch agent + health probe).
  metrics_namespace = "SentinelOps"
  instance_id       = aws_instance.main.id
  # Basic monitoring only reports every 5 minutes.
  metric_period = var.detailed_monitoring ? 60 : 300
}

# ---------- notifications ----------

resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"
}

# AWS emails a confirmation link; nothing is delivered until you click it.
resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ---------- logs ----------

resource "aws_cloudwatch_log_group" "demo_app" {
  name              = "/${var.project_name}/demo-app"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "dashboard" {
  name              = "/${var.project_name}/dashboard"
  retention_in_days = var.log_retention_days
}

# ---------- alarms ----------

resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name          = "${var.project_name}-high-cpu"
  alarm_description   = "Average CPU above ${var.cpu_alarm_threshold}% (try: scripts/chaos.sh cpu)."
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  dimensions          = { InstanceId = local.instance_id }
  statistic           = "Average"
  period              = local.metric_period
  evaluation_periods  = 2
  threshold           = var.cpu_alarm_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# Self-healing level 3: if AWS's own hardware/host check fails, CloudWatch
# moves the instance to healthy hardware (same ID, IP and disk).
resource "aws_cloudwatch_metric_alarm" "system_status_check" {
  alarm_name          = "${var.project_name}-system-status-check-recover"
  alarm_description   = "AWS host problem: the instance is recovered automatically."
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed_System"
  dimensions          = { InstanceId = local.instance_id }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  alarm_actions = [
    "arn:aws:automate:${var.aws_region}:ec2:recover",
    aws_sns_topic.alerts.arn,
  ]
}

# Problems inside the instance (kernel, out of memory, network config).
# AWS cannot fix these by moving hardware, so this one only notifies.
resource "aws_cloudwatch_metric_alarm" "instance_status_check" {
  alarm_name          = "${var.project_name}-instance-status-check"
  alarm_description   = "The instance itself is failing its status check."
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed_Instance"
  dimensions          = { InstanceId = local.instance_id }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 3
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# The health probe on the instance (installed by user_data.sh) publishes
# DemoAppHealthy = 1 or 0 every minute while the production container exists.
resource "aws_cloudwatch_metric_alarm" "demo_app_unhealthy" {
  alarm_name          = "${var.project_name}-demo-app-unhealthy"
  alarm_description   = "Production demo-app /health failed for 3 minutes in a row."
  namespace           = local.metrics_namespace
  metric_name         = "DemoAppHealthy"
  dimensions          = { Environment = "production" }
  statistic           = "Minimum"
  period              = 60
  evaluation_periods  = 3
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  # No data = no production container yet, or the instance is stopped.
  treat_missing_data = "notBreaching"
  alarm_actions      = [aws_sns_topic.alerts.arn]
  ok_actions         = [aws_sns_topic.alerts.arn]
}

# ---------- dashboard ----------

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = var.project_name

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "CPU utilization (%)"
          region  = var.aws_region
          stat    = "Average"
          period  = local.metric_period
          metrics = [["AWS/EC2", "CPUUtilization", "InstanceId", local.instance_id]]
          yAxis   = { left = { min = 0, max = 100 } }
          annotations = {
            horizontal = [{ label = "alarm", value = var.cpu_alarm_threshold }]
          }
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Memory and disk used (%)"
          region = var.aws_region
          period = 60
          metrics = [
            [local.metrics_namespace, "mem_used_percent", "InstanceId", local.instance_id, { label = "memory" }],
            # Disk has extra dimensions (path, fstype); a search finds it without hard-coding them.
            [{ expression = "SEARCH('{${local.metrics_namespace},InstanceId,fstype,path} MetricName=\"disk_used_percent\" InstanceId=\"${local.instance_id}\"', 'Average', 60)", id = "disk", label = "disk /" }],
          ]
          yAxis = { left = { min = 0, max = 100 } }
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "demo-app production health (1 = healthy)"
          region  = var.aws_region
          stat    = "Minimum"
          period  = 60
          metrics = [[local.metrics_namespace, "DemoAppHealthy", "Environment", "production"]]
          yAxis   = { left = { min = 0, max = 1 } }
        }
      },
      {
        type   = "alarm"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title = "Alarm states"
          alarms = [
            aws_cloudwatch_metric_alarm.high_cpu.arn,
            aws_cloudwatch_metric_alarm.system_status_check.arn,
            aws_cloudwatch_metric_alarm.instance_status_check.arn,
            aws_cloudwatch_metric_alarm.demo_app_unhealthy.arn,
          ]
        }
      },
    ]
  })
}
