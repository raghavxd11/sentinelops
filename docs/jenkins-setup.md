# Jenkins setup

One-time setup after `terraform apply`. Takes about 15 minutes. Terraform has already installed Jenkins, Docker, Trivy, Python 3.11, git and jq on the instance, and given Jenkins the AWS settings (`/etc/sentinelops.env`), so nothing about AWS is entered here.

Values used below come from `terraform output` in the `terraform/` folder: `<IP>` is `public_ip`.

## 1. Check the instance is ready

```powershell
ssh -i <path-to-key>.pem ec2-user@<IP>
```

```bash
sudo tail -n 3 /var/log/user-data.log     # last line: "SentinelOps bootstrap finished"
systemctl is-active docker jenkins        # active / active
docker compose version; trivy --version; python3.11 --version
sudo cat /var/lib/jenkins/secrets/initialAdminPassword
```

## 2. Unlock Jenkins and install plugins

1. Open `http://<IP>:8080`, paste the initial admin password.
2. Choose **Install suggested plugins**. This includes Pipeline, Git, GitHub Branch Source, Credentials Binding, Timestamper, Workspace Cleanup and Pipeline Graph View.
3. Create the admin user. Keep Jenkins URL as `http://<IP>:8080/`.
4. **Manage Jenkins > Plugins > Available plugins**: install **JUnit** and **Coverage** (test and coverage reports; skip one if it is already listed under Installed plugins). Restart when asked.

Jenkins is reachable only from your IP and GitHub's webhook ranges (security group), and requires login.

## 3. Credentials

**Manage Jenkins > Credentials > System > Global credentials > Add Credentials**

| Kind | ID | Value | Used for |
|---|---|---|---|
| Secret text | `sentinelops-api-token` | the `API_TOKEN` the dashboard on the instance runs with | `report.sh` (header `X-API-Token`) |
| Username with password | `github` | your GitHub username + a fine-grained personal access token | scanning the repository and pull requests |

Create the GitHub token at GitHub > Settings > Developer settings > Fine-grained tokens: only the `sentinelops` repository, permissions **Contents: Read**, **Metadata: Read**, **Pull requests: Read**, **Commit statuses: Read and write** (lets Jenkins mark commits and PRs green/red). Without a token the public repository still builds, but GitHub's anonymous API limit (60 requests/hour) makes branch scans fail.

The pipeline never needs AWS keys: the instance role gives Jenkins access to ECR, SNS and CloudWatch.

## 4. Create the multibranch pipeline

1. **New Item** > name `sentinelops` > **Multibranch Pipeline** > OK.
2. **Branch Sources > Add source > GitHub**
   - Credentials: `github`
   - Repository HTTPS URL: `https://github.com/raghavxd11/sentinelops`
   - Behaviours: keep *Discover branches* and *Discover pull requests from origin*. Add **Advanced clone behaviours** and tick **Fetch tags**, so the app version shows the release tag (`git describe`).
3. **Build Configuration**: by Jenkinsfile, script path `Jenkinsfile`.
4. **Scan Multibranch Pipeline Triggers**: tick *Periodically if not otherwise run*, interval **1 minute**. This is the fallback if the webhook does not get through (same effect as `pollSCM`).
5. **Orphaned Item Strategy**: discard old items, keep 5.
6. Save. Jenkins scans GitHub and starts a build for each branch with a Jenkinsfile.

Each branch builds with these steps: Checkout, Setup, Lint | Unit tests | Dependency scan, Build, Image scan; then for `dev` and `main` only: Push, (Approval on `main`), Deploy, Health check.

## 5. GitHub webhook (builds start within seconds of a push)

GitHub repository > **Settings > Webhooks > Add webhook**

- Payload URL: `http://<IP>:8080/github-webhook/` (the trailing slash matters)
- Content type: `application/json`
- Events: **Pushes** and **Pull requests**

After saving, *Recent Deliveries* should show a green tick (HTTP 200). If it fails, the 1-minute periodic scan from step 4 still picks up pushes.

## 6. Branches

The pipeline deploys `dev` to staging and `main` to production:

```bash
git checkout -b dev
git push -u origin dev
```

Workflow: `feature/*` branch > pull request into `dev` (checks run on the PR) > merge, which deploys to staging > pull request `dev` into `main` > merge > approve in Jenkins, which deploys to production.

Optional, recommended: GitHub > Settings > Branches > add a rule for `main` and `dev` requiring the Jenkins status check to pass before merging.

## 7. Before the first deployment

- The dashboard must be running on the instance on port 5000 (`DASHBOARD_URL`, default `http://localhost:5000`) with the same `API_TOKEN` as the Jenkins credential, and a service named **`demo-app`** on its Services page. Otherwise the run still deploys, but the report step prints a warning.
- Confirm the SNS subscription email, or notifications are not delivered.
- The first `main` run has nothing to roll back to. A failed health check is then reported as `FAILED` instead of `ROLLED_BACK`. After one healthy deploy, `latest-stable` exists in ECR and rollbacks work.

## 8. Run it

- **Build Now** on the `dev` or `main` job. On `main` the run pauses at **Approval**: open the run and click **Deploy** (or Abort, which records nothing).
- Build parameters appear after the first run (**Build with Parameters**):
  - `BREAK_HEALTH`: deploy with a failing `/health` to watch the automatic rollback.
  - `DOCKERFILE = Dockerfile.vulnerable`: build `demo-app/Dockerfile.vulnerable` to watch Trivy block the image.
- Results: the stage graph on each run (Pipeline Overview), **Tests** and **Coverage** on each run, Trivy reports under **Build Artifacts** (`reports/`), the deployment on the dashboard, and an email from SNS.

## What the pipeline uses on the instance

| Item | Where it comes from |
|---|---|
| `AWS_REGION`, `ECR_REPOSITORY_URL`, `SNS_TOPIC_ARN`, `DEMO_APP_LOG_GROUP`, `DASHBOARD_URL` | `/etc/sentinelops.env`, written by Terraform, loaded into the Jenkins service via `/etc/systemd/system/jenkins.service.d/sentinelops.conf` |
| AWS permissions | EC2 instance role (`terraform/iam.tf`) |
| Docker access | `jenkins` user is in the `docker` group |
| Dashboard token | Jenkins credential `sentinelops-api-token` |

To change a value (for example `DASHBOARD_URL`), edit `/etc/sentinelops.env` and run `sudo systemctl restart jenkins`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `permission denied ... docker.sock` | `sudo usermod -aG docker jenkins && sudo systemctl restart jenkins` |
| `ECR_REPOSITORY_URL` is empty in the log | `sudo systemctl show jenkins -p EnvironmentFiles` should list `/etc/sentinelops.env`; then `sudo systemctl daemon-reload && sudo systemctl restart jenkins` |
| `No such DSL method 'recordCoverage'` | Install the Coverage plugin (step 2) |
| Dependency scan fails while downloading the vulnerability database | Temporary registry rate limit; run the build again |
| Image scan fails on HIGH/CRITICAL | A real finding: read `reports/trivy-image.txt`, update the base image or the package, push again |
| Webhook deliveries show a timeout | Check the security group still allows GitHub's ranges (`enable_github_webhook = true`); the periodic scan is the fallback |
| `report.sh` warning `HTTP 401` | Jenkins credential and dashboard `API_TOKEN` differ |
| `report.sh` warning `HTTP 404 unknown service` | Add a service called `demo-app` on the dashboard's Services page |
