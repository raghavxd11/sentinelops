# SentinelOps

Self-healing CI/CD platform on AWS. Every push is tested, scanned, containerized and deployed automatically. Failed deployments roll back on their own, crashed containers restart themselves, and every deployment is traceable to its Git commit.

## 🛠️ Tech Stack
- Git & GitHub
- Jenkins
- Docker
- AWS (EC2, ECR, CloudWatch, SNS)
- Python (Flask) + MySQL

## Run the dashboard locally

Commands are for Windows PowerShell, run from the repository root. Needs Python 3.11 or newer.

### 1. Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r dashboardequirements-dev.txt
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
