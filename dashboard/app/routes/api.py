"""REST API. Jenkins reports deployments here; everything returns JSON."""
import hmac
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import text

from ..extensions import db
from ..metrics import compute_stats
from ..models import DEPLOYMENT_STATUSES, STAGES, Deployment, Service, open_incident_for

bp = Blueprint("api", __name__)


def token_is_valid():
    """Compare the X-API-Token header with API_TOKEN in constant time.

    hmac.compare_digest takes the same time whether the first or the last
    character is wrong, so the token cannot be guessed by timing responses.
    """
    expected = current_app.config.get("API_TOKEN") or ""
    supplied = request.headers.get("X-API-Token", "")
    if not expected:
        return False
    return hmac.compare_digest(supplied.encode(), expected.encode())


def parse_timestamp(value):
    """ISO 8601 string -> UTC datetime without tzinfo (how the DB stores times)."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def error(message, code):
    return jsonify({"error": message}), code


@bp.route("/health")
def health():
    """Used by Docker HEALTHCHECK. Also checks the database answers."""
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        return jsonify({"status": "unhealthy", "database": "unreachable"}), 503
    return jsonify({"status": "ok", "database": "ok"})


@bp.route("/api/stats")
def stats():
    return jsonify(compute_stats())


@bp.route("/api/deployments", methods=["GET"])
def list_deployments():
    query = Deployment.query.join(Service)

    status = request.args.get("status")
    if status:
        if status not in DEPLOYMENT_STATUSES:
            return error(f"status must be one of {DEPLOYMENT_STATUSES}", 400)
        query = query.filter(Deployment.status == status)

    service = request.args.get("service")
    if service:
        query = query.filter(Service.name == service)

    limit = min(request.args.get("limit", 50, type=int), 200)
    deployments = query.order_by(Deployment.created_at.desc()).limit(limit).all()
    return jsonify([d.to_dict() for d in deployments])


@bp.route("/api/deployments", methods=["POST"])
def report_deployment():
    if not token_is_valid():
        return error("missing or invalid X-API-Token header", 401)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("request body must be a JSON object", 400)

    # --- validate ---
    for field in ("service", "commit_hash", "status"):
        if not data.get(field):
            return error(f"'{field}' is required", 400)

    status = data["status"]
    if status not in DEPLOYMENT_STATUSES:
        return error(f"status must be one of {DEPLOYMENT_STATUSES}", 400)

    failed_stage = data.get("failed_stage") or None
    if failed_stage is not None and failed_stage not in STAGES:
        return error(f"failed_stage must be one of {STAGES}", 400)

    try:
        build_number = int(data["build_number"]) if data.get("build_number") is not None else None
        duration = (
            int(data["duration_seconds"]) if data.get("duration_seconds") is not None else None
        )
        committed_at = parse_timestamp(data["committed_at"]) if data.get("committed_at") else None
    except (TypeError, ValueError):
        return error(
            "build_number and duration_seconds must be integers, committed_at must be ISO 8601",
            400,
        )

    service = Service.query.filter_by(name=data["service"]).first()
    if service is None:
        return error(f"unknown service '{data['service']}'. Add it on the Services page.", 404)

    # --- save ---
    # If the pipeline reported this build as IN_PROGRESS earlier, update that row
    # with the final result instead of adding a second one.
    deployment = None
    if build_number is not None:
        deployment = Deployment.query.filter_by(
            service_id=service.id, build_number=build_number, status="IN_PROGRESS"
        ).first()
    created = deployment is None
    if created:
        deployment = Deployment(service=service)
        db.session.add(deployment)

    commit_hash = str(data["commit_hash"])[:40]
    deployment.commit_hash = commit_hash
    deployment.commit_author = str(data.get("commit_author") or "")[:120]
    deployment.commit_message = str(data.get("commit_message") or "")[:500]
    deployment.branch = str(data.get("branch") or "")[:120]
    deployment.build_number = build_number
    deployment.image_tag = str(data.get("image_tag") or commit_hash[:7])[:200]
    deployment.status = status
    deployment.failed_stage = failed_stage
    deployment.duration_seconds = duration
    deployment.committed_at = committed_at

    # --- auto-incident ---
    incident = None
    if status in ("FAILED", "ROLLED_BACK"):
        incident = open_incident_for(deployment)

    db.session.commit()

    body = deployment.to_dict()
    body["incident_id"] = incident.id if incident else None
    return jsonify(body), 201 if created else 200
