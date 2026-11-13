# Printed after `terraform apply`; show again any time with `terraform output`.

output "public_ip" {
  description = "Elastic IP of the server."
  value       = aws_eip.main.public_ip
}

output "jenkins_url" {
  description = "Jenkins UI. The first admin password is in /var/lib/jenkins/secrets/initialAdminPassword."
  value       = "http://${aws_eip.main.public_ip}:8080"
}

output "dashboard_url" {
  description = "SentinelOps dashboard."
  value       = "http://${aws_eip.main.public_ip}:5000"
}

output "demo_app_production_url" {
  value = "http://${aws_eip.main.public_ip}:8000"
}

output "demo_app_staging_url" {
  value = "http://${aws_eip.main.public_ip}:8001"
}

output "ecr_repository_url" {
  description = "Where Jenkins pushes demo-app images."
  value       = aws_ecr_repository.demo_app.repository_url
}

output "sns_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "cloudwatch_dashboard_url" {
  value = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}

output "ssh_command" {
  description = "Only works if key_name was set."
  value       = "ssh -i <path-to-your-key>.pem ec2-user@${aws_eip.main.public_ip}"
}
