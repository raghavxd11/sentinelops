# SentinelOps

Self-healing CI/CD platform on AWS. Every push is linted, tested and scanned with Trivy, built into a Docker image tagged with its Git commit, pushed to Amazon ECR and deployed to EC2 by Jenkins. If the new version fails its health check, the pipeline rolls back to the last stable image on its own. Crashed or hung containers restart themselves, and every deployment is reported to a web dashboard that traces it back to its commit.

## Architecture

```mermaid
flowchart LR
    dev[Developer] -->|push / pull request| gh[GitHub]
    gh -->|webhook| jenkins

    subgraph ec2 [EC2 t3.medium, created by Terraform]
        jenkins[Jenkins pipeline]
        prod[demo-app production :8000]
        stg[demo-app staging :8001]
        dash[Dashboard :5000 + MySQL]
        heal[autoheal]
    end

    jenkins -->|push commit tag, move latest-stable| ecr[(Amazon ECR)]
    ecr -->|pull| prod
    ecr -->|pull| stg
    jenkins -->|deploy, health check, rollback| prod
    jenkins -->|deploy, health check, rollback| stg
    jenkins -->|POST /api/deployments| dash
    heal -->|restart unhealthy| prod
    jenkins -->|build result| sns[SNS email]
    prod -.->|logs, health metric| cw[CloudWatch logs, metrics, alarms, dashboard]
    cw -->|alarm| sns
    cw -->|status check failed: recover| ec2
```

**Pipeline** ([Jenkinsfile](Jenkinsfile)): Checkout → Setup → Lint (flake8) ‖ Unit tests + coverage (pytest) ‖ Dependency scan (Trivy) → Docker build → Image scan (Trivy, fails on fixable HIGH/CRITICAL) → Push to ECR → Approval (`main` only) → Deploy → Health check (5 tries, backoff) → tag `latest-stable` **or** roll back → report to the dashboard + SNS email.

`dev` deploys to staging (port 8001), `main` deploys to production (port 8000) after a manual approval. Feature branches and pull requests run every check up to the image scan.

**Self-healing, three levels**

| Level | Failure | What heals it |
|---|---|---|
| Application | New version fails `/health` after deploy | `scripts/rollback.sh` redeploys the last image tagged stable in ECR and re-checks health |
| Container | Process crashes / app hangs | Docker restart policy `unless-stopped` / Docker HEALTHCHECK + autoheal container |
| Infrastructure | AWS host fails the system status check | CloudWatch alarm with the `ec2:recover` action |

## Project structure

```
sentinelops/
├── dashboard/                 # Flask dashboard: UI, REST API, MySQL/SQLite, pytest suite
│   ├── app/                   # app factory, models, routes, templates, static files
│   ├── tests/
│   ├── seed.py                # demo data (marked is_seed), --clear removes it
│   └── wsgi.py
├── demo-app/                  # small Flask service the pipeline deploys
│   ├── app.py                 # /, /health, /api/info; BREAK_HEALTH=true breaks /health
│   ├── tests/
│   └── Dockerfile
├── Jenkinsfile                # declarative pipeline (repo root, found by Jenkins)
├── scripts/
│   ├── common.sh              # per-environment settings shared by the scripts
│   ├── deploy.sh              # run an image as the production/staging container
│   ├── healthcheck.sh         # GET /health with retries and exponential backoff
│   ├── rollback.sh            # redeploy the stable image, verify health
│   ├── report.sh              # POST the pipeline result to the dashboard API
│   └── chaos.sh               # crash / hang / CPU stress / broken deploy, for demos
├── terraform/                 # EC2, ECR, IAM, security group, SNS, CloudWatch (see its README)
├── monitoring/
│   └── cloudwatch-agent.json  # memory and disk metrics from the instance
├── docs/
│   └── jenkins-setup.md       # plugins, credentials, multibranch job, webhook
├── .env.example               # dashboard settings (copy to .env)
├── .gitattributes             # LF line endings for scripts, Terraform, Docker, YAML
└── LICENSE
```

## Tech stack

| Area | Tools |
|---|---|
| Application | Python 3.11, Flask, Flask-Login, Flask-WTF (CSRF), Flask-SQLAlchemy, Jinja, Bootstrap 5, Chart.js |
| Database | MySQL 8 (Docker); SQLite for quick local runs and unit tests |
| Quality and security | pytest + coverage, flake8, Trivy (dependency and image scans), ECR scan on push |
| Containers | Docker, Docker Compose, autoheal |
| CI/CD | Jenkins declarative multibranch pipeline, GitHub webhook |
| Infrastructure as Code | Terraform (AWS provider 6) |
| AWS | EC2, ECR, IAM role + instance profile, Security Group, Elastic IP, CloudWatch Logs / alarms / dashboard, SNS |

## Status

Work in progress for a college DevOps project (demo on 16 Nov 2026).

- [x] Dashboard: auth, services / deployments / incidents CRUD, REST API, automatic incidents, DevOps metrics, 106 tests
- [x] demo-app with tests (15), including the broken-health case
- [x] demo-app Dockerfile (non-root user, HEALTHCHECK)
- [ ] Dashboard Dockerfile and `docker-compose.yml` (MySQL + dashboard + demo-app + autoheal)
- [x] Terraform for all AWS resources: written, `terraform fmt` and `terraform validate` pass. Not applied yet.
- [x] Jenkinsfile: passes the Jenkins declarative linter. Not run on the real Jenkins yet.
- [x] Deploy, health check, rollback, report and chaos scripts: pass shellcheck and were tested against local Docker
- [ ] Deployed on AWS and every demo scenario run end to end
- [ ] `docs/RESULTS.md` with measured results, `docs/demo-guide.md`

## Documentation

- [terraform/README.md](terraform/README.md): resources, estimated cost, apply / stop / destroy
- [docs/jenkins-setup.md](docs/jenkins-setup.md): Jenkins plugins, credentials, multibranch pipeline, webhook

## Run the dashboard locally

Commands are for Windows PowerShell, run from the repository root. Needs Python 3.11 or newer.

### 1. Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r dashboard\requirements-dev.txt
```

If PowerShell refuses to run `Activate.ps1`, allow scripts for this window only and try again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 2. Configure

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Open `.env` and paste the generated value as `SECRET_KEY`. Set `API_TOKEN` to any long random string. `.env` is ignored by git.

### 3. Start

```powershell
cd dashboard
python seed.py     # optional: demo data and the login admin / sentinel-demo
python wsgi.py
```

Open http://127.0.0.1:5000. Without `DATABASE_URL` the app uses a SQLite file (`dashboard\instance\sentinelops.db`), which is enough for a quick look. Tables are created on first start.

Seeded rows are marked as demo data in the UI. Remove them with `python seed.py --clear`; real pipeline data is kept.

### 4. Use MySQL instead of SQLite

Production runs on MySQL 8. To use it locally, start one in Docker (port 3307, so it does not clash with a MySQL already installed on 3306):

```powershell
docker run -d --name sentinelops-mysql -p 127.0.0.1:3307:3306 `
  -e MYSQL_DATABASE=sentinelops -e MYSQL_USER=sentinel `
  -e MYSQL_PASSWORD=local-dev-only -e MYSQL_ROOT_PASSWORD=local-dev-only mysql:8
```

Wait about 20 seconds for MySQL to start, then point the app at it and start it as in step 3:

```powershell
$env:DATABASE_URL = "mysql+pymysql://sentinel:local-dev-only@127.0.0.1:3307/sentinelops"
python seed.py
python wsgi.py
```

Remove the database when finished: `docker rm -f sentinelops-mysql`.

### 5. Report a deployment by hand

This is the request Jenkins sends at the end of a pipeline run. The service must exist on the Services page (`seed.py` creates `demo-app`). Replace the token with the `API_TOKEN` from `.env`.

```powershell
$body = @{ service = "demo-app"; commit_hash = "7c1e4b9d2f0a8e6b5c3d1f4a9b8e7d6c5b4a3f21"
           status = "ROLLED_BACK"; build_number = 48; branch = "main" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/deployments `
  -Headers @{ "X-API-Token" = "your-api-token" } -ContentType "application/json" -Body $body
```

The deployment appears on the Deployments page and, because it was rolled back, an incident is opened for it. All endpoints are listed on the API docs page of the dashboard.

### 6. Test and lint

```powershell
cd dashboard
python -m pytest
python -m flake8 .
```

Tests use an in-memory SQLite database. To run the same tests against MySQL, create an empty database that is used only for tests (every table in it is dropped after each test) and pass its URL:

```powershell
docker exec sentinelops-mysql mysql -uroot -plocal-dev-only -e "CREATE DATABASE sentinelops_test; GRANT ALL ON sentinelops_test.* TO 'sentinel'@'%';"
$env:TEST_DATABASE_URL = "mysql+pymysql://sentinel:local-dev-only@127.0.0.1:3307/sentinelops_test"
python -m pytest
```
