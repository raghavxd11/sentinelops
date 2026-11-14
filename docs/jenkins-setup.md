# Jenkins setup and demos

How to go from a fresh server to a working pipeline, and how to run each demo.
Everything here runs on the one EC2 server (`184.196.222.54`, Amazon Linux 2023,
AWS Academy Learner Lab, `us-east-1`).

| What | Where |
|------|-------|
| Jenkins | `http://184.196.222.54:8080` |
| Dashboard (mysql + dashboard + autoheal, from `docker-compose.prod.yml`) | `http://184.196.222.54:5000` |
| demo-app (deployed only by the pipeline, container name `demo-app`) | `http://184.196.222.54:8000` |
| ECR repository | `567190388316.dkr.ecr.us-east-1.amazonaws.com/sentinelops/demo-app` |

The server already has Jenkins, Docker, Compose, Trivy, python3.11, jq and git
(from `terraform/user_data.sh`). Its AWS access comes from the
`LabInstanceProfile` instance profile, so no AWS keys are stored anywhere: not
in Jenkins and not in the repo.

## How the pipeline works

`Jenkinsfile` (repo root), one run per push to `main`:

| # | Stage | What happens | If it fails |
|---|-------|--------------|-------------|
| 1 | Checkout | `checkout scm`, then reads commit hash, author, message, time | FAILED, stage Checkout |
| 2 | Test | Creates a python3.11 venv, runs `pytest` for demo-app, publishes JUnit results and archives a coverage XML | FAILED, stage Test |
| 3 | Build | `docker build` of `demo-app/<DOCKERFILE>`, tag = short commit SHA, labels = full commit + build number | FAILED, stage Build |
| 4 | Scan | `trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1`; report archived as `reports/trivy-image.txt` | FAILED, stage Scan. Nothing is pushed or deployed |
| 5 | Push | `aws ecr get-login-password \| docker login`, then `docker push` | FAILED, stage Push |
| 6 | Deploy | `scripts/deploy.sh` replaces the `demo-app` container on port 8000 | FAILED, stage Deploy |
| 7 | Health check | `scripts/healthcheck.sh http://localhost:8000/health 5 5` (5 tries, 5 s apart) | see below |

The Health check stage then takes one of three paths:

- **Healthy:** the image is also tagged and pushed as `latest-stable` in ECR. Build result **SUCCESS**.
- **Unhealthy:** `scripts/rollback.sh` pulls `latest-stable`, redeploys it with `deploy.sh` and runs `healthcheck.sh` again. Build result **UNSTABLE** (yellow), description "ROLLED_BACK…", dashboard status **ROLLED_BACK**.
- **Unhealthy, and no `latest-stable` exists yet** (first deploy) or the stable image is unhealthy too: `rollback.sh` exits non-zero. Build result **FAILURE**, dashboard status FAILED at stage Health check.

`post { always }` archives `reports/**` and calls `scripts/report.sh`, which
POSTs the result to the dashboard (`/api/deployments`). FAILED and ROLLED_BACK
results create an OPEN incident on the dashboard automatically. A failed
report only prints a WARNING and never changes the build result.
`post { cleanup }` runs `cleanWs()`.

Plugins used, all from Jenkins' "suggested plugins" set: Pipeline, Git,
GitHub (`githubPush()`), Credentials Binding (`withCredentials`), Timestamper
(`timestamps()`), Workspace Cleanup (`cleanWs()`), JUnit (`junit`).

## 1. Start the dashboard stack on the server

Skip this if `docker compose -f docker-compose.prod.yml ps` already shows all
three containers healthy.

```bash
ssh -i labsuser.pem ec2-user@184.196.222.54

git clone https://github.com/raghavxd11/sentinelops.git   # first time only
cd sentinelops
git pull

# Secrets file (never committed). Generate the two random values:
cp .env.example .env
python3.11 -c "import secrets; print(secrets.token_hex(32))"      # -> SECRET_KEY
python3.11 -c "import secrets; print(secrets.token_urlsafe(32))"  # -> API_TOKEN
nano .env      # paste both, set MYSQL_PASSWORD and MYSQL_ROOT_PASSWORD (letters and numbers only)
chmod 600 .env

docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps     # mysql, dashboard, autoheal: healthy
curl http://localhost:5000/health                # {"database":"ok","status":"ok"}
```

Then, in the browser at `http://184.196.222.54:5000`:

1. **Register** an account and log in.
2. **Services → New service**, name exactly **`demo-app`** (the pipeline reports
   under this name; any other name gives HTTP 404 "unknown service"),
   health URL `http://184.196.222.54:8000/health`, repo URL
   `https://github.com/raghavxd11/sentinelops`.

Keep the `API_TOKEN` value from `.env`. Jenkins needs the same value in step 3.

## 2. Check the server before the first build

The pipeline runs as the `jenkins` Linux user, so check as that user:

```bash
sudo -u jenkins docker ps                       # must list containers, not "permission denied"
sudo -u jenkins aws sts get-caller-identity     # must show ...assumed-role/LabRole/...
sudo -u jenkins trivy --version                 # 0.76.2
sudo -u jenkins python3.11 --version
sudo -u jenkins jq --version
```

If `docker ps` says permission denied: `sudo usermod -aG docker jenkins && sudo systemctl restart jenkins`
(group changes only apply after Jenkins restarts).

## 3. Jenkins: first login and the API token credential

1. Open `http://184.196.222.54:8080`. Unlock it with
   `sudo cat /var/lib/jenkins/secrets/initialAdminPassword`, choose
   **Install suggested plugins**, create the admin user.
2. **Manage Jenkins → System → Jenkins URL**: `http://184.196.222.54:8080/` → Save.
3. **Manage Jenkins → Plugins → Installed plugins**: check that **JUnit** is
   there (it normally comes with the suggested set). Install it only if missing.
4. **Manage Jenkins → Credentials → System → Global credentials → Add Credentials**:
   - Kind: **Secret text**
   - Secret: the `API_TOKEN` value from the server's `.env`
   - ID: **`dashboard-api-token`** (exactly this; the Jenkinsfile looks it up by ID)
   - Description: `SentinelOps dashboard API token`

Jenkins stores it encrypted and masks it as `****` in build logs.

## 4. Create the pipeline job

1. **New Item** → name `sentinelops` → **Pipeline** → OK.
2. **General**: tick **GitHub project**, URL `https://github.com/raghavxd11/sentinelops/`.
3. **Triggers**: tick **GitHub hook trigger for GITScm polling**.
   (The Jenkinsfile also declares `githubPush()`, which sets this after the first run anyway.)
4. **Pipeline**:
   - Definition: **Pipeline script from SCM**
   - SCM: **Git**, Repository URL `https://github.com/raghavxd11/sentinelops.git`
     (public repo, no credentials needed)
   - Branch Specifier: `*/main`
   - Script Path: `Jenkinsfile`
5. Save, then **Build Now** once.

The first build:

- registers the parameters, so later runs show **Build with Parameters**;
- must be a normal, healthy build: it creates the first `latest-stable` image.
  Until that exists, a failed health check cannot be rolled back.

Check: the build is green, `curl http://localhost:8000/api/info` on the server shows
the commit, and the dashboard's Deployments page shows a SUCCESS row with build #1.

## 5. GitHub webhook

In the GitHub repo: **Settings → Webhooks → Add webhook**:

- Payload URL: `http://184.196.222.54:8080/github-webhook/` (the trailing `/` matters)
- Content type: `application/json`
- Which events: **Just the push event**
- Active: ticked → **Add webhook**

GitHub sends a test ping right away. **Recent Deliveries** should show a green
tick (HTTP 200). The security group lets GitHub's webhook IP ranges reach port
8080. If deliveries time out, check that `github_webhook_cidrs` in
`terraform.tfvars` is current (`curl https://api.github.com/meta | jq .hooks`).

## 6. Demos

Every demo ends on the dashboard: **Deployments** shows the row (click it for the full
trace: commit, author, message, branch, build number, image tag, status, duration,
failed stage), **Incidents** shows the auto-created incident for failures.

### A. Push → automatic deploy

```bash
# on your laptop: any small change to demo-app, e.g. a word in the page text in app.py
git commit -am "feat: change demo-app page text"
git push origin main
```

Jenkins starts within seconds (webhook). All 7 stages pass. Then:

```bash
curl http://184.196.222.54:8000/api/info    # git_commit = the commit you just pushed
```

Dashboard: new SUCCESS deployment with that commit hash and author.

### B. Broken deploy → automatic rollback

Jenkins → `sentinelops` → **Build with Parameters** → tick **BREAK_HEALTH** → Build.

What to show in the console log:

1. Deploy starts the new image with `BREAK_HEALTH=true`.
2. `healthcheck.sh` gets HTTP 500 five times and fails.
3. `rollback.sh` redeploys `latest-stable` and prints `ROLLBACK OK`.
4. Build is **UNSTABLE** (yellow) with description "ROLLED_BACK to latest-stable".

```bash
curl -i http://184.196.222.54:8000/health    # 200 again
curl http://184.196.222.54:8000/api/info     # commit of the last good build, not this one
```

Dashboard: ROLLED_BACK deployment (failed stage Health check) plus a new OPEN incident.
Resolve the incident on the Incidents page with a root-cause note to feed the MTTR metric.

### C. Trivy blocks a vulnerable image

**Build with Parameters** → DOCKERFILE = **Dockerfile.vulnerable** → Build.

The Scan stage prints the CVE table and fails. Push, Deploy and Health check are
skipped, so nothing reaches ECR or the server. The full report is under the build's
**Artifacts** → `reports/trivy-image.txt`. Dashboard: FAILED at stage Scan, plus an incident.
The running demo-app is untouched (`/api/info` still shows the last good commit).

### D. Container self-healing (no Jenkins involved)

The pipeline starts demo-app with `--restart unless-stopped` and the label
`autoheal=true`, so both healing mechanisms apply to it:

```bash
# crash: the main process exits -> Docker's restart policy starts it again
docker exec demo-app sh -c 'kill 1'
docker ps --filter name=demo-app            # "Up 2 seconds"

# hang: running but /health returns 500 -> autoheal restarts it after ~30 s
docker exec demo-app touch /tmp/break-health
watch -n 2 'docker ps --filter name=demo-app'   # (unhealthy) -> restarted -> (healthy)
docker logs sentinelops-autoheal-1 | tail -3
```

Details and measured timings: [docker.md → Self-healing](docker.md#self-healing-three-levels).
Don't use `docker kill` / `docker stop` for this: Docker treats those as a deliberate stop and does not restart.

### E. First deploy with no stable version (optional, explains the edge case)

Only possible before any build has passed: if the very first build has BREAK_HEALTH
ticked, `rollback.sh` prints `ROLLBACK NOT POSSIBLE ... Usually this is the first deploy`
and exits 2, so the build is FAILED, not ROLLED_BACK.

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `WARNING: deployment not reported ... HTTP 401` | The `dashboard-api-token` credential doesn't match `API_TOKEN` in the server's `.env`. |
| `... HTTP 404 unknown service 'demo-app'` | Create the `demo-app` service on the dashboard (step 1). |
| `... could not reach http://localhost:5000` | Dashboard stack is down: `docker compose -f docker-compose.prod.yml up -d`. |
| `permission denied ... /var/run/docker.sock` | `jenkins` user is not in the `docker` group (step 2). |
| Push: `no basic auth credentials` or `AccessDenied` | Instance profile missing or the Learner Lab session expired. Start the lab again; `sudo -u jenkins aws sts get-caller-identity` must work. |
| Webhook does nothing | Check GitHub → Webhooks → Recent Deliveries; the Payload URL needs the trailing `/github-webhook/`. |
| Build with Parameters missing | Run the job once with Build Now; the parameters come from the Jenkinsfile. |

After the Learner Lab session ends the instance stops. When it starts again, Jenkins
starts on boot and the containers come back by themselves (`restart: unless-stopped`).
