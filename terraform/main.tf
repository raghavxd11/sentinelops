# Terraform and provider setup, plus lookups shared by the other files.
#
# State is kept locally (terraform.tfstate, gitignored). Remote state in S3 is
# a planned upgrade, not needed for a single-person project.

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # Every resource gets these tags, so the project is easy to find in the console
  # and in Cost Explorer.
  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "terraform"
    }
  }
}

# Use the default VPC and its subnets. One public instance does not need a
# custom network, and the default VPC exists in every region.
data "aws_vpc" "default" {
  default = true
}

# Latest Amazon Linux 2023 image (x86_64). Docker, Java, Python 3.11 and the
# CloudWatch agent are all available from its package repositories.
data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}
