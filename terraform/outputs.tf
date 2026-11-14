# Printed after "terraform apply". Show again any time with "terraform output".

output "public_ip" {
  description = "Fixed public IP of the server."
  value       = aws_eip.server.public_ip
}

output "ssh_command" {
  description = "Log in to the server (labsuser.pem is downloaded from AWS Details)."
  value       = "ssh -i labsuser.pem ec2-user@${aws_eip.server.public_ip}"
}

output "jenkins_url" {
  value = "http://${aws_eip.server.public_ip}:8080"
}

output "dashboard_url" {
  value = "http://${aws_eip.server.public_ip}:5000"
}

output "demo_app_url" {
  value = "http://${aws_eip.server.public_ip}:8000"
}

output "ecr_repository_url" {
  description = "Where Jenkins pushes demo-app images."
  value       = aws_ecr_repository.demo_app.repository_url
}