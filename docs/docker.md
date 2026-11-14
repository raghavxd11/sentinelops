# Docker in SentinelOps

This page explains every Docker file in the repo, how to run the stack locally
and on the EC2 server, how the containers heal themselves, and how Trivy scans
the images.

## The files at a glance

| File | What it does |
|------|--------------|
| `demo-app/Dockerfile` | Builds the demo-app image (the app the pipeline deploys). |
| `demo-app/Dockerfile.vulnerable` | Same app on an old, unpatched base image. Only for the "Trivy blocks the build" demo. Never deployed. |
| `dashboard/Dockerfile` | Builds the dashboard image (UI + REST API). |
| `demo-app/.dockerignore`, `dashboard/.dockerignore` | Files Docker must not copy into the image: tests, caches, the local venv, `.env`, the local SQLite file. Keeps images small and secrets out. |
| `docker-compose.yml` | Local stack: MySQL + dashboard + demo-app + autoheal, one command. |
| `docker-compose.prod.yml` | EC2 server stack: MySQL + dashboard + autoheal. demo-app is deployed by Jenkins instead. |
| `.env.example` | Lists the settings (secrets) both compose files read from `.env`. Copy it to `.env`. `.env` is never committed. |

## The Dockerfiles

Both app images follow the same steps:

1. **`FROM python:3.11-slim`**: a small official Python image based on Debian. "slim" leaves out compilers and docs, so there is less to attack and less to download.
2. **`ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1`**: no `.pyc` files, and logs appear immediately in `docker logs`.
3. **`RUN apt-get update && apt-get upgrade -y ...`**: installs Debian security fixes released after the base image was built. Without this line, Trivy found a HIGH zlib CVE in the newest `python:3.11-slim` (November 2026).
4. **`COPY requirements.txt` then `pip install`**: dependencies are installed *before* the code is copied. Docker caches each step (layer), so changing the code does not reinstall all packages.
5. **`RUN pip uninstall -y setuptools`**: setuptools is only needed to *install* packages. It contains old copies of `wheel` and `jaraco.context` with HIGH CVEs, so it is removed.
6. **`COPY` the code** (`app.py` for demo-app; `app/`, `wsgi.py`, `seed.py` for the dashboard).
7. **`useradd appuser` + `USER appuser`**: the app does not run as root. If someone breaks into the app, they are not root inside the container.
8. **`EXPOSE`**: documents the port (8000 demo-app, 5000 dashboard).
9. **`HEALTHCHECK`**: every 10 s Docker calls `/health` inside the container. After 3 failures in a row the container is marked `unhealthy`. It uses Python's `urllib`, because the slim image has no `curl`. The dashboard's `/health` also checks that the database answers.
10. **`CMD gunicorn ...`**: gunicorn is a production web server. Flask's built-in server is only for development.

Dashboard-only detail: `gunicorn --workers 2 --preload`. With two workers, both
used to run `CREATE TABLE` at the same moment on a fresh MySQL database. MySQL
rejected one of them, and the container crashed once on first start.
`--preload` loads the app (and creates the tables) once, before the workers
start. `wsgi.py` then closes that first database connection, so each worker
opens its own.

## Running locally

```bash
cp .env.example .env          # then put real values in .env
docker compose up --build -d  # build images, start all 4 containers
docker compose ps             # all should say "(healthy)" after ~30 s
```

- Dashboard: http://localhost:5000
- demo-app: http://localhost:8000
- MySQL has no published port. Only the dashboard can reach it, over Docker's internal network, using the name `mysql`.
- Data lives in the named volume `mysql-data`, so it survives `docker compose down`. `docker compose down -v` deletes it.
- Optional demo data: `docker compose exec dashboard python seed.py` (remove it with `python seed.py --clear`).

`depends_on: condition: service_healthy` makes the dashboard wait until MySQL
answers `mysqladmin ping`, not just until the MySQL container has started.

## Running on the EC2 server (`docker-compose.prod.yml`)

The server already has Docker, Compose and git (installed by
`terraform/user_data.sh`), and `ec2-user` is in the `docker` group.

```bash
# 1. Log in (Learner Lab key vockey, downloaded as labsuser.pem)
ssh -i labsuser.pem ec2-user@<elastic-ip>

# 2. Get the code
git clone https://github.com/raghavxd11/sentinelops.git
cd sentinelops

# 3. Create the secrets file (never committed)
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # paste as SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))" # paste as API_TOKEN
nano .env      # also set MYSQL_PASSWORD and MYSQL_ROOT_PASSWORD (letters and numbers only)
chmod 600 .env

# 4. Build the dashboard on the server and start everything
docker compose -f docker-compose.prod.yml up -d --build

# 5. Check
docker compose -f docker-compose.prod.yml ps
curl http://localhost:5000/health        # {"database":"ok","status":"ok"}
```

The dashboard is then at `http://<elastic-ip>:5000`.

- **Update after a `git pull`:** run the same `up -d --build` command again. Only changed containers are recreated, and the database volume is kept.
- **Stop:** `docker compose -f docker-compose.prod.yml down` (data kept).
- **After a server reboot:** Docker starts at boot (`systemctl enable docker`), and `restart: unless-stopped` starts the containers again.
- If `.env` is missing a value, Compose refuses to start and names the variable (the `${VAR:?...}` syntax). It never runs MySQL with an empty password.

Why demo-app is not in this file: the Jenkins pipeline deploys demo-app itself,
with `docker run`, using the image it just pushed to ECR (tagged with the
commit SHA). That is how it can roll back to an older image. The pipeline
must start the container with `--restart unless-stopped --label autoheal=true`
so both self-healing mechanisms below also cover it. This was tested: a
container started with plain `docker run --label autoheal=true` was healed by
the prod autoheal container in 36 s.

## Self-healing: three levels

| Level | What fails | What heals it | Status |
|-------|------------|---------------|--------|
| 1. Application | A new version fails its health check after a deploy | Jenkins runs `scripts/rollback.sh` and redeploys the `latest-stable` image | Pipeline phase (next) |
| 2. Container | The process crashes, or keeps running but stops answering correctly | Docker restart policy + HEALTHCHECK + autoheal | **Done, tested below** |
| 3. Infrastructure | The EC2 instance fails its AWS status check | CloudWatch alarm with the `ec2:recover` action | Not built yet (no alarm in `terraform/` yet) |

### Level 2a: crashed container → restart policy

`restart: unless-stopped` tells Docker: whenever this container's main process
exits, start it again, unless a person stopped it on purpose.

Demo (the main process exits, like an app crash):

```bash
docker exec sentinelops-demo-app-1 sh -c 'kill 1'
docker ps            # "Up 2 seconds": it came back by itself
docker inspect -f '{{.RestartCount}}' sentinelops-demo-app-1    # goes up by 1
```

On the EC2 server you can also do a hard crash (SIGKILL from outside), which
was tested too:

```bash
sudo kill -9 $(docker inspect -f '{{.State.Pid}}' <container>)
```

**Do not use `docker kill` or `docker stop` for this demo.** Docker treats
them as "a person stopped it on purpose" and does *not* restart the container.
This was tested: after `docker kill`, the container stayed `exited`.

### Level 2b: running but unhealthy → autoheal

The restart policy only reacts when the process *exits*. A process can keep
running but be broken (hung, out of connections, returning 500). For that:

1. `HEALTHCHECK` in the Dockerfile marks the container `unhealthy` after 3 failed `/health` checks.
2. Docker itself does **not** restart unhealthy containers (only Docker Swarm does).
3. The `autoheal` container (`willfarrell/autoheal`) watches the Docker socket. Every 5 s it looks for containers that have the label `autoheal=true` and are `unhealthy`, and restarts them.

Demo, without rebuilding anything:

```bash
docker exec sentinelops-demo-app-1 touch /tmp/break-health
curl -i localhost:8000/health        # 500 right away
docker ps                            # after ~25 s: "(unhealthy)", then autoheal restarts it
docker logs sentinelops-autoheal-1   # "found to be unhealthy - Restarting container now"
curl -i localhost:8000/health        # 200 again
```

How it works: `/health` returns 500 while the file `/tmp/break-health` exists.
A restart keeps the container's files, so the app deletes that file when it
starts. The restart really fixes the problem, just like restarting a hung
process. Otherwise autoheal would restart it forever. This is different from
`BREAK_HEALTH=true`: that env var is set when a container is *created*, and is
used for the "broken deploy → rollback" demo.

Measured locally (Docker 29.8, 14 Nov 2026):

| Step | Time after `touch /tmp/break-health` |
|------|------|
| `/health` returns 500 | immediately |
| Docker marks container `unhealthy` | 23 s |
| autoheal restarts it | 28 s |
| healthy again, flag file gone | 34 s |

The time to `unhealthy` comes from the HEALTHCHECK settings: 3 failed checks,
10 s apart. autoheal checks every 5 s.

**Windows Git Bash note:** Git Bash rewrites `/tmp/...` into a Windows path, so
the `touch` silently goes nowhere. Run the commands in PowerShell, or prefix
them with `MSYS_NO_PATHCONV=1`. Not an issue on the EC2 server.

## Image scanning with Trivy

Trivy compares every OS package and Python package in an image with a database
of known vulnerabilities (CVEs). The pipeline fails the build if it finds any
HIGH or CRITICAL ones:

```bash
trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 <image>
```

`--ignore-unfixed` skips CVEs that have no fix yet. We cannot do anything
about those, and they would keep the pipeline red forever. Anything that
*does* have a fix must be fixed before the image can ship.

Without installing Trivy (locally, through Docker, same version as the server):

```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache \
  aquasec/trivy:0.76.2 image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 sentinelops-demo-app
```

Results on 14 Nov 2026 (Trivy 0.76.2):

| Image | Result |
|-------|--------|
| `sentinelops-demo-app` before the fixes | **failed**: zlib1g (2 HIGH), wheel + jaraco.context bundled in setuptools (2 HIGH) |
| `sentinelops-demo-app` (current Dockerfile) | **passed**, exit code 0 |
| `sentinelops-dashboard` (current Dockerfile) | **passed**, exit code 0 |
| `demo-app:vulnerable` (`Dockerfile.vulnerable`) | **failed**, exit code 1: 129 OS findings on Debian 11.1 (103 HIGH, 26 CRITICAL) + 4 HIGH in Python packages |

New CVEs are published every day, so an image that passes today can fail next
week. That is expected: the fix is usually to rebuild (`apt-get upgrade` picks
up the new patches) or to bump a version in `requirements.txt`.

### "Trivy blocks the build" demo

```bash
docker build -f demo-app/Dockerfile.vulnerable -t demo-app:vulnerable demo-app
trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 demo-app:vulnerable
echo $?     # 1 → in Jenkins this fails the stage, so nothing is pushed or deployed
```
