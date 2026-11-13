"""Demo data so the dashboard is never empty during a local demo.

    python seed.py           insert demo data (replaces any earlier demo data)
    python seed.py --clear   remove demo data, keep real pipeline data

Every deployment and incident inserted here has is_seed=True, and the dashboard
shows a "demo data" note while any such row exists. Rows reported by Jenkins
have is_seed=False and are never touched by this script.
"""
import os
import random
import sys
from datetime import timedelta

from app import create_app
from app.extensions import db
from app.models import Deployment, Incident, Service, User, open_incident_for, utcnow

REPO_URL = "https://github.com/raghavxd11/sentinelops"

# The two environments the pipeline deploys to (dev branch -> staging, main -> production).
SERVICES = [
    {
        "name": "demo-app",
        "description": "Production container, deployed from main after manual approval",
        "repo_url": REPO_URL,
        "health_url": "http://localhost:8000/health",
        "branch": "main",
        "first_build": 12,
    },
    {
        "name": "demo-app-staging",
        "description": "Staging container, deployed automatically from dev",
        "repo_url": REPO_URL,
        "health_url": "http://localhost:8001/health",
        "branch": "dev",
        "first_build": 31,
    },
]

AUTHORS = ["Raghav Pandey", "Raghav Pandey", "Raghav Pandey", "Ananya Sharma", "Karan Mehta"]

SUCCESS_MESSAGES = [
    "feat: show git commit on the index page",
    "fix: return JSON content type from /health",
    "test: cover /api/info with missing env vars",
    "chore: run container as non-root user",
    "ci: publish coverage report from Jenkins",
    "fix: use exec form for CMD so SIGTERM reaches gunicorn",
    "docs: document BREAK_HEALTH flag",
    "feat: add uptime to /api/info",
    "chore: add HEALTHCHECK to Dockerfile",
    "refactor: read version from APP_VERSION once at startup",
    "ci: tag image with short commit SHA",
    "fix: healthcheck.sh exits non-zero after last retry",
    "chore: slim runtime stage, drop build tools",
    "ci: archive Trivy report as build artifact",
    "feat: add version badge to index page",
    "fix: trim trailing newline from GIT_COMMIT",
    "test: add broken-health test case",
    "chore: bump Flask to 3.1.3",
    "ci: retry ECR push once on network error",
    "style: fix flake8 warnings in app.py",
    "feat: return hostname in /api/info",
    "fix: handle missing APP_VERSION with 'unknown'",
    "ci: add timeout to deploy stage",
    "chore: add .dockerignore",
    "test: assert /health returns 200 by default",
    "ci: fail image scan on HIGH and CRITICAL only",
    "docs: add local run steps to README",
    "fix: rollback.sh pulls latest-stable before run",
    "chore: label image with commit and build number",
    "ci: clean workspace in post step",
    "feat: log version on startup",
    "fix: quote commit message in report.sh",
    "ci: run lint, tests and fs scan in parallel",
    "chore: pin gunicorn worker count to 2",
    "test: check index page shows version",
    "ci: send SNS notification on failure",
    "fix: deploy.sh removes old container before run",
    "chore: set restart policy to unless-stopped",
    "docs: describe staging and production ports",
    "ci: add manual approval before production",
]

# (commit message, root cause written when the incident was resolved)
ROLLBACKS = [
    (
        "feat: read greeting from GREETING env var",
        "Container started without GREETING set and /health returned 500 because the "
        "config check raised KeyError. Added a default value and a test for the missing "
        "variable.",
    ),
    (
        "chore: move gunicorn settings to gunicorn.conf.py",
        "New config file bound gunicorn to 127.0.0.1 instead of 0.0.0.0, so the health "
        "check from the host could not connect. Restored the bind address.",
    ),
    (
        "feat: add request logging middleware",
        "Logging middleware raised on requests without a User-Agent header, which "
        "includes the health checker. Replaced the dict lookup with .get().",
    ),
    (
        "fix: make /health check dependencies",
        "The dependency check had no timeout and /health hung until the health check "
        "gave up (5/5 failed). Added a 2 second timeout.",
    ),
]

# (failed stage, commit message, root cause)
FAILURES = [
    (
        "Test",
        "refactor: move version lookup into config",
        "test_info_returns_commit failed: GIT_COMMIT was read at import time, before "
        "the test set it. Moved the lookup inside the request handler.",
    ),
    (
        "Scan",
        "chore: pin base image to python:3.9-slim-buster",
        "Trivy image scan reported HIGH vulnerabilities with fixes available in the old "
        "Debian base image. Reverted to python:3.11-slim.",
    ),
    (
        "Test",
        "feat: add /api/info endpoint",
        "Two tests failed: the response key was 'commit' but the tests expected "
        "'git_commit'. Renamed the key.",
    ),
    (
        "Build",
        "chore: reorder Dockerfile layers for better caching",
        "docker build failed: COPY requirements.txt ran before WORKDIR in the builder "
        "stage. Fixed the layer order.",
    ),
    (
        "Scan",
        "chore: add requests for outbound checks",
        "Trivy filesystem scan flagged a HIGH CVE in the pinned requests version. "
        "Bumped to the patched release.",
    ),
]


def clear():
    """Delete seeded deployments and incidents. Real pipeline rows are kept."""
    seeded_ids = [d.id for d in Deployment.query.filter_by(is_seed=True)]
    if seeded_ids:
        # A real incident linked to a seeded deployment keeps existing, just unlinked.
        Incident.query.filter(
            Incident.is_seed.is_(False), Incident.deployment_id.in_(seeded_ids)
        ).update({"deployment_id": None}, synchronize_session=False)
    incidents = Incident.query.filter_by(is_seed=True).delete()
    deployments = Deployment.query.filter_by(is_seed=True).delete()
    db.session.commit()
    return deployments, incidents


def get_or_create_services():
    services = {}
    for spec in SERVICES:
        service = Service.query.filter_by(name=spec["name"]).first()
        if service is None:
            service = Service(
                name=spec["name"],
                description=spec["description"],
                repo_url=spec["repo_url"],
                health_url=spec["health_url"],
            )
            db.session.add(service)
        services[spec["name"]] = service
    return services


def get_or_create_admin():
    """Local login for the demo. Returns the password only if the user was created."""
    if User.query.filter_by(username="admin").first():
        return None
    password = os.environ.get("SEED_ADMIN_PASSWORD", "sentinel-demo")
    user = User(username="admin", email="admin@sentinelops.local")
    user.set_password(password)
    db.session.add(user)
    return password


def seed():
    clear()
    rng = random.Random(42)  # fixed seed: the same demo data every run
    now = utcnow()
    services = get_or_create_services()
    password = get_or_create_admin()

    # 1. Pick a time and an environment for each deployment over the last 14 days.
    slots = []
    for days_ago in range(13, -1, -1):
        for _ in range(rng.choice([1, 2, 3, 3, 4, 5])):
            when = now - timedelta(days=days_ago, minutes=rng.randint(30, 9 * 60))
            spec = SERVICES[0] if rng.random() < 0.4 else SERVICES[1]
            slots.append((when, spec))
    slots.sort(key=lambda slot: slot[0])

    # 2. Create the deployments, oldest first, so build numbers go up over time.
    #    Random positions get the rollbacks and failures; everything else succeeds.
    build_numbers = {spec["name"]: spec["first_build"] for spec in SERVICES}
    problems = [("ROLLED_BACK", None) + case for case in ROLLBACKS]
    problems += [("FAILED",) + case for case in FAILURES]
    problem_at = dict(zip(rng.sample(range(len(slots)), len(problems)), problems))
    messages = rng.sample(SUCCESS_MESSAGES, len(SUCCESS_MESSAGES))  # shuffled copy
    root_causes = {}
    for position, (when, spec) in enumerate(slots):
        if position in problem_at:
            status, failed_stage, message, cause = problem_at[position]
        else:
            status, failed_stage, cause = "SUCCESS", None, None
            message = messages[position % len(messages)]

        if status == "ROLLED_BACK":
            duration = rng.randint(205, 290)  # five health check retries, then rollback
        elif failed_stage == "Test":
            duration = rng.randint(35, 60)
        elif failed_stage == "Build":
            duration = rng.randint(62, 90)
        elif failed_stage == "Scan":
            duration = rng.randint(95, 130)
        else:
            duration = rng.randint(140, 230)

        # main waits for manual approval, so commit -> deploy takes longer there.
        wait = rng.randint(180, 2400) if spec["branch"] == "main" else rng.randint(15, 90)
        commit_hash = f"{rng.getrandbits(160):040x}"
        deployment = Deployment(
            service=services[spec["name"]],
            commit_hash=commit_hash,
            commit_author=rng.choice(AUTHORS),
            commit_message=message,
            branch=spec["branch"],
            build_number=build_numbers[spec["name"]],
            image_tag=commit_hash[:7],
            status=status,
            failed_stage=failed_stage,
            duration_seconds=duration,
            committed_at=when - timedelta(seconds=duration + wait),
            created_at=when,
            is_seed=True,
        )
        build_numbers[spec["name"]] += 1
        db.session.add(deployment)
        if cause:
            root_causes[deployment] = cause

    # One build that is still running, on staging.
    staging = SERVICES[1]
    commit_hash = f"{rng.getrandbits(160):040x}"
    db.session.add(
        Deployment(
            service=services[staging["name"]],
            commit_hash=commit_hash,
            commit_author="Raghav Pandey",
            commit_message="feat: report deployment to dashboard from Jenkins",
            branch=staging["branch"],
            build_number=build_numbers[staging["name"]],
            image_tag=commit_hash[:7],
            status="IN_PROGRESS",
            committed_at=now - timedelta(minutes=3),
            created_at=now - timedelta(minutes=2),
            is_seed=True,
        )
    )

    # 3. Incidents: the same auto-incident logic the API uses. The two newest stay
    #    open; older ones were resolved with a root-cause note.
    broken = sorted(root_causes, key=lambda d: d.created_at)
    for position, deployment in enumerate(broken):
        incident = open_incident_for(deployment)
        incident.created_at = deployment.created_at + timedelta(seconds=rng.randint(2, 8))
        if position < len(broken) - 2:
            incident.status = "RESOLVED"
            incident.resolved_at = incident.created_at + timedelta(minutes=rng.randint(9, 95))
            incident.root_cause = root_causes[deployment]

    # One incident raised by hand, not linked to a deployment.
    opened = now - timedelta(days=6, hours=3)
    db.session.add(
        Incident(
            service=services["demo-app-staging"],
            title="Jenkins workspace disk at 87% on build host",
            severity="LOW",
            status="RESOLVED",
            root_cause="Old images and build cache were never pruned. Added "
            "'docker image prune -f' to the pipeline post step.",
            created_at=opened,
            resolved_at=opened + timedelta(minutes=26),
            is_seed=True,
        )
    )

    db.session.commit()
    return password


def main():
    app = create_app()
    with app.app_context():
        if "--clear" in sys.argv:
            deployments, incidents = clear()
            print(f"Removed {deployments} seeded deployments and {incidents} seeded incidents.")
            return

        password = seed()
        print(
            f"Seeded {Deployment.query.filter_by(is_seed=True).count()} deployments and "
            f"{Incident.query.filter_by(is_seed=True).count()} incidents "
            f"across {Service.query.count()} services."
        )
        if password:
            print(f"Created login  admin / {password}  (local demo only)")
        else:
            print("User 'admin' already exists, password unchanged.")


if __name__ == "__main__":
    main()
