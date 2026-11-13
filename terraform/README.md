# Terraform: SentinelOps on AWS

One `terraform apply` creates everything the pipeline needs. `terraform destroy` removes all of it.

| File | What it creates |
|---|---|
| `main.tf` | AWS provider, default tags, lookups for the default VPC and the latest Amazon Linux 2023 image |
| `variables.tf` | All inputs. Required: `my_ip_cidr`, `alert_email` |
| `security.tf` | Security group: 22 and 8080 from your IP (8080 also from GitHub webhook ranges); 5000, 8000, 8001 open |
| `ec2.tf` | t3.medium instance (IMDSv2, encrypted 30 GiB gp3 disk) and an Elastic IP |
| `user_data.sh` | First-boot script: Docker + Compose + Buildx, Jenkins (Java 21), Trivy, Python 3.11, CloudWatch agent, health probe |
| `iam.tf` | Instance role: ECR push/pull on one repository, write to two log groups, metrics in one namespace, publish to one SNS topic |
| `ecr.tf` | `sentinelops/demo-app` repository, scan on push, lifecycle policy (keep 10, never expire the stable tags) |
| `monitoring.tf` | SNS topic + email, log groups, 4 alarms (CPU, system check with auto-recover, instance check, demo-app health), CloudWatch dashboard |
| `outputs.tf` | Public IP, Jenkins / dashboard / app URLs, ECR URL, SNS ARN, CloudWatch dashboard link |
| `../monitoring/cloudwatch-agent.json` | CloudWatch agent config (memory and disk used %), embedded into `user_data.sh` |

The instance picks up the ECR URL, SNS topic and region from `/etc/sentinelops.env`, written by `user_data.sh` from Terraform values. Jenkins loads the same file through a systemd drop-in, so no AWS settings or access keys are typed into Jenkins.

## Estimated cost

Region `ap-south-1` (Mumbai), on-demand, prices before tax. **These are estimates, not measured bills.** Check them in the [AWS Pricing Calculator](https://calculator.aws/) before applying, and watch the real spend in Billing > Bills.

| Resource | Price | Per day running | Per day stopped |
|---|---|---|---|
| EC2 t3.medium | ≈ $0.0448 / hour | ≈ $1.08 | $0 |
| EBS gp3 30 GiB | ≈ $0.09 / GiB-month | ≈ $0.09 | ≈ $0.09 |
| Elastic IP (public IPv4) | $0.005 / hour, also while stopped | $0.12 | $0.12 |
| EC2 detailed monitoring | ≈ $0.30 / metric-month, about 7 metrics | ≈ $0.07 | ≈ $0.07 |
| CloudWatch custom metrics (memory, disk, health) | first 10 metrics free | $0 | $0 |
| CloudWatch alarms (4) | first 10 free, then $0.10 / alarm-month | $0 | $0 |
| CloudWatch dashboard (1) | first 3 free, then $3 / month | $0 | $0 |
| CloudWatch Logs | ≈ $0.50–0.70 / GB ingested, 5 GB / month free | ≈ $0 | $0 |
| ECR storage | $0.10 / GB-month (10 images of ~60 MB) | < $0.01 | < $0.01 |
| SNS email | first 1,000 emails / month free | $0 | $0 |
| **Total** | | **≈ $1.40** | **≈ $0.30** |

About $1.40 per day while the instance runs, so roughly $5 for the three project days if it is stopped overnight and destroyed after the demo. Leaving it running for a full month would cost about $40. The CPU stress demo can use t3 "unlimited" burst credits; a 10-minute run costs at most a few cents.

## Before the first apply

1. Install Terraform ≥ 1.6 and the AWS CLI, then sign in: `aws configure` (an IAM user with admin rights on your own account is fine for creating the resources).
2. In the EC2 console, create a key pair named `sentinelops-key` (Key pairs > Create, .pem) and keep the file outside the repository.
3. Create your variables file:

   ```powershell
   cd terraform
   Copy-Item terraform.tfvars.example terraform.tfvars
   (Invoke-RestMethod https://checkip.amazonaws.com).Trim()   # your IP; add /32
   ```

   Edit `terraform.tfvars`: `my_ip_cidr`, `alert_email`, `key_name`. It is gitignored.

## Apply

```powershell
terraform init
terraform plan -out tfplan      # read what will be created (17 resources)
terraform apply tfplan
terraform output
```

Then:

- Confirm the "AWS Notification - Subscription Confirmation" email, or no alerts arrive.
- Wait about 5 minutes for `user_data.sh`. Check progress over SSH: `sudo tail -f /var/log/user-data.log` (ends with `SentinelOps bootstrap finished`).
- Open `jenkins_url` and continue with [docs/jenkins-setup.md](../docs/jenkins-setup.md).

If your IP changes (new network), update `my_ip_cidr` and run `terraform apply` again; only the security group changes.

## Stop overnight, start again

Stopping keeps the disk, Jenkins configuration, images and the Elastic IP; only the instance hours stop.

```powershell
$id = aws ec2 describe-instances --filters "Name=tag:Name,Values=sentinelops-server" "Name=instance-state-name,Values=running,stopped" --query "Reservations[0].Instances[0].InstanceId" --output text
aws ec2 stop-instances  --instance-ids $id
aws ec2 start-instances --instance-ids $id
```

Docker, Jenkins and the containers (restart policy `unless-stopped`) come back on their own after a start.

## Destroy

```powershell
terraform destroy
```

This deletes the instance, disk, Elastic IP, ECR repository with all images (`force_delete`), log groups, alarms, dashboard, SNS topic and IAM role. Afterwards, check that nothing is left: EC2 > Instances shows `terminated`, and Billing shows no new charges the next day. The key pair is not managed by Terraform; delete it in the console if you no longer need it.

## Validate without touching AWS

```powershell
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```
