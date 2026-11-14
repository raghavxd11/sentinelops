# Settings for this project. Change values here instead of editing every file.

variable "aws_region" {
  description = "AWS region to create everything in (Learner Lab uses us-east-1)."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Name used in resource names and tags."
  type        = string
  default     = "sentinelops"
}

variable "github_webhook_cidrs" {
  description = "GitHub's webhook IP ranges, so GitHub can reach Jenkins on port 8080."
  type        = list(string)
}

variable "my_ip_cidr" {
  description = "Your public IP in CIDR form, e.g. 1.2.3.4/32. SSH and Jenkins are only open to this."
  type        = string
}