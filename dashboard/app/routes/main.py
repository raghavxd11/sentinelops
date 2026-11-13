"""Landing page, Overview dashboard and the API docs page."""
from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..metrics import compute_stats, deployments_per_day
from ..models import Deployment, Incident

bp = Blueprint("main", __name__)


@bp.route("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for("main.overview"))
    return render_template("landing.html")


@bp.route("/overview")
@login_required
def overview():
    stats = compute_stats()
    chart_data = {
        "per_day": deployments_per_day(days=14),
        "breakdown": stats["status_breakdown"],
    }
    recent = Deployment.query.order_by(Deployment.created_at.desc()).limit(8).all()
    open_incidents = (
        Incident.query.filter_by(status="OPEN")
        .order_by(Incident.created_at.desc())
        .limit(6)
        .all()
    )
    return render_template(
        "overview.html",
        stats=stats,
        chart_data=chart_data,
        recent=recent,
        open_incidents=open_incidents,
    )


@bp.route("/api-docs")
@login_required
def api_docs():
    # Example responses on the page are real rows from the database.
    latest = Deployment.query.order_by(Deployment.created_at.desc()).first()
    return render_template(
        "api_docs.html",
        base_url=request.host_url.rstrip("/"),
        latest=latest.to_dict() if latest else None,
        stats=compute_stats(),
    )
