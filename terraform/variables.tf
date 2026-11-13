# Inputs. Set the required ones (no default) in terraform.tfvars,
# see terraform.tfvars.example.

variable "aws_region" {
  description = "AWS region for every resource."
  type        = string
  default     = "ap-south-1"
}

variable "project_name" {
  description = "Prefix for resource names and the Project tag."
  type        = string
  default     = "sentinelops"
}

variable "my_ip_cidr" {
  description = "Your public IP as a /32 CIDR, e.g. 203.0.113.7/32. SSH and Jenkins only accept this address."
  type        = string

  validation {
    condition     = can(cidrhost(var.my_ip_cidr, 0)) && endswith(var.my_ip_cidr, "/32")
    error_message = "my_ip_cidr must be a single IPv4 address in CIDR form, ending in /32."
  }
}

variable "alert_email" {
  description = "Email address for alarm and pipeline notifications. AWS sends a confirmation link first."
  type        = string
}

variable "key_name" {
  description = "Name of an existing EC2 key pair for SSH. Leave null to launch without SSH key access."
  type        = string
  default     = null
}

variable "instance_type" {
  description = "EC2 size. t3.medium (2 vCPU, 4 GiB) is the smallest that runs Jenkins, Docker builds and the apps together."
  type        = string
  default     = "t3.medium"
}

variable "root_volume_size" {
  description = "Root disk size in GiB (Jenkins workspace, Docker images, Trivy database)."
  type        = number
  default     = 30
}

variable "enable_github_webhook" {
  description = "Open Jenkins (8080) to GitHub's webhook IP ranges so pushes trigger builds."
  type        = bool
  default     = true
}

variable "github_webhook_cidrs" {
  description = "GitHub webhook source ranges (IPv4), from the \"hooks\" list at https://api.github.com/meta."
  type        = list(string)
  default = [
    "192.30.252.0/22",
    "185.199.108.0/22",
    "140.82.112.0/20",
    "143.55.64.0/20",
    "9.234.98.160/28",
    "9.234.98.176/28",
    "9.234.106.48/28",
  ]
}

variable "app_ports_cidrs" {
  description = "Who can reach the dashboard (5000), production (8000) and staging (8001). Open by default for the demo."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "ecr_repository_name" {
  description = "ECR repository for demo-app images."
  type        = string
  default     = "sentinelops/demo-app"
}

variable "ecr_keep_images" {
  description = "How many images the ECR lifecycle policy keeps (images tagged as stable are always kept)."
  type        = number
  default     = 10
}

variable "log_retention_days" {
  description = "How long CloudWatch keeps container logs."
  type        = number
  default     = 7
}

variable "detailed_monitoring" {
  description = "1-minute EC2 metrics instead of 5-minute, so the CPU alarm fires within minutes during the demo."
  type        = bool
  default     = true
}

variable "cpu_alarm_threshold" {
  description = "Average CPU percent that triggers the high-CPU alarm."
  type        = number
  default     = 80
}

# Tool versions installed by user_data.sh. Pinned so a rebuild installs the same thing.
variable "trivy_version" {
  description = "Trivy release installed on the instance."
  type        = string
  default     = "0.76.2"
}

variable "docker_compose_version" {
  description = "Docker Compose plugin release."
  type        = string
  default     = "5.7.1"
}

variable "docker_buildx_version" {
  description = "Docker Buildx plugin release (BuildKit builds)."
  type        = string
  default     = "0.39.0"
}
