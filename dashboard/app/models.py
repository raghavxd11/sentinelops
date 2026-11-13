"""Database tables: User, Service, Deployment, Incident."""
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

DEPLOYMENT_STATUSES = ["SUCCESS", "FAILED", "ROLLED_BACK", "IN_PROGRESS"]
SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
INCIDENT_STATUSES = ["OPEN", "RESOLVED"]

# Pipeline stages in order, as shown on the deployment detail page.
STAGES = ["Checkout", "Test", "Build", "Scan", "Push", "Deploy", "Health check"]


def utcnow():
    """Current UTC time without tzinfo. Every timestamp in the DB is stored like this."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Service(db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=False, default="")
    repo_url = db.Column(db.String(255), nullable=False, default="")
    health_url = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    # Deleting a service also deletes its deployments and incidents.
    deployments = db.relationship(
        "Deployment", back_populates="service", cascade="all, delete-orphan"
    )
    incidents = db.relationship(
        "Incident", back_populates="service", cascade="all, delete-orphan"
    )

    @property
    def deploy_count(self):
        return Deployment.query.filter_by(service_id=self.id).count()

    @property
    def last_deployment(self):
        return (
            Deployment.query.filter_by(service_id=self.id)
            .order_by(Deployment.created_at.desc())
            .first()
        )


class Deployment(db.Model):
    __tablename__ = "deployments"

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)
    commit_hash = db.Column(db.String(40), nullable=False)
    commit_author = db.Column(db.String(120), nullable=False, default="")
    commit_message = db.Column(db.String(500), nullable=False, default="")
    branch = db.Column(db.String(120), nullable=False, default="")
    build_number = db.Column(db.Integer)
    image_tag = db.Column(db.String(200), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, index=True)
    # Stage that failed (one of STAGES). Only set when Jenkins reports it.
    failed_stage = db.Column(db.String(40))
    duration_seconds = db.Column(db.Integer)
    # When the commit was made. Used for lead time (commit -> deploy).
    committed_at = db.Column(db.DateTime)
    # When the pipeline reported this deployment.
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    # True for rows inserted by seed.py (demo data), false for real pipeline runs.
    is_seed = db.Column(db.Boolean, nullable=False, default=False)

    service = db.relationship("Service", back_populates="deployments")
    incidents = db.relationship("Incident", back_populates="deployment")

    @property
    def short_hash(self):
        return self.commit_hash[:7]

    def previous_stable(self):
        """Last successful deployment of the same service before this one."""
        return (
            Deployment.query.filter(
                Deployment.service_id == self.service_id,
                Deployment.status == "SUCCESS",
                Deployment.created_at < self.created_at,
            )
            .order_by(Deployment.created_at.desc())
            .first()
        )

    def stages(self):
        """Pipeline timeline as a list of (stage name, state).

        States: passed, failed, skipped, running, unknown.
        The timeline is derived from the final status and failed_stage, because
        Jenkins reports one result per deployment, not one per stage.
        """
        if self.status == "SUCCESS":
            return [(name, "passed") for name in STAGES]

        if self.status == "IN_PROGRESS":
            return [(name, "running") for name in STAGES]

        if self.status == "ROLLED_BACK":
            # Everything passed until the health check, then the rollback ran.
            timeline = [(name, "passed") for name in STAGES[:-1]]
            return timeline + [("Health check", "failed"), ("Rollback", "passed")]

        # FAILED
        if self.failed_stage not in STAGES:
            return [(name, "unknown") for name in STAGES]
        failed_at = STAGES.index(self.failed_stage)
        timeline = []
        for position, name in enumerate(STAGES):
            if position < failed_at:
                timeline.append((name, "passed"))
            elif position == failed_at:
                timeline.append((name, "failed"))
            else:
                timeline.append((name, "skipped"))
        return timeline

    def to_dict(self):
        return {
            "id": self.id,
            "service": self.service.name,
            "commit_hash": self.commit_hash,
            "commit_author": self.commit_author,
            "commit_message": self.commit_message,
            "branch": self.branch,
            "build_number": self.build_number,
            "image_tag": self.image_tag,
            "status": self.status,
            "failed_stage": self.failed_stage,
            "duration_seconds": self.duration_seconds,
            "committed_at": iso(self.committed_at),
            "created_at": iso(self.created_at),
        }


class Incident(db.Model):
    __tablename__ = "incidents"

    id = db.Column(db.Integer, primary_key=True)
    deployment_id = db.Column(db.Integer, db.ForeignKey("deployments.id"))
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    severity = db.Column(db.String(20), nullable=False, default="MEDIUM")
    status = db.Column(db.String(20), nullable=False, default="OPEN", index=True)
    root_cause = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    resolved_at = db.Column(db.DateTime)
    is_seed = db.Column(db.Boolean, nullable=False, default=False)

    service = db.relationship("Service", back_populates="incidents")
    deployment = db.relationship("Deployment", back_populates="incidents")

    def resolve(self):
        self.status = "RESOLVED"
        self.resolved_at = utcnow()


def iso(value):
    """Datetime -> ISO 8601 string in UTC, or None."""
    return value.isoformat() + "Z" if value else None


def open_incident_for(deployment):
    """Create an OPEN incident for a FAILED or ROLLED_BACK deployment.

    A rollback means a broken version reached the server, so it is HIGH.
    A failure earlier in the pipeline never reached the server, so it is MEDIUM.
    """
    build = f"build #{deployment.build_number}" if deployment.build_number else "build"
    name = deployment.service.name

    if deployment.status == "ROLLED_BACK":
        title = f"Health check failed on {name}, {build} rolled back"
        severity = "HIGH"
    elif deployment.failed_stage:
        title = f"{name} {build} failed at {deployment.failed_stage} stage"
        severity = "MEDIUM"
    else:
        title = f"{name} {build} failed"
        severity = "MEDIUM"

    incident = Incident(
        deployment=deployment,
        service=deployment.service,
        title=title,
        severity=severity,
        status="OPEN",
        is_seed=deployment.is_seed,
    )
    db.session.add(incident)
    return incident
