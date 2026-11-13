"""Deployments: filterable list and the detail page with the full trace."""
from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import or_

from ..extensions import db
from ..models import DEPLOYMENT_STATUSES, Deployment, Service

bp = Blueprint("deployments", __name__, url_prefix="/deployments")

PER_PAGE = 25


@bp.route("")
@login_required
def list_deployments():
    status = request.args.get("status", "")
    search = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    query = Deployment.query.join(Service)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Deployment.commit_hash.like(f"{search}%"),
                Deployment.commit_message.ilike(pattern),
                Deployment.commit_author.ilike(pattern),
                Deployment.image_tag.ilike(pattern),
                Deployment.branch.ilike(pattern),
                Service.name.ilike(pattern),
            )
        )

    # Counts shown on the filter pills (they respect the search text).
    counts = {s: query.filter(Deployment.status == s).count() for s in DEPLOYMENT_STATUSES}
    counts["ALL"] = sum(counts.values())

    if status in DEPLOYMENT_STATUSES:
        query = query.filter(Deployment.status == status)
    else:
        status = ""

    pagination = query.order_by(*Deployment.newest_first()).paginate(
        page=page, per_page=PER_PAGE, error_out=False
    )
    return render_template(
        "deployments/list.html",
        pagination=pagination,
        deployments=pagination.items,
        status=status,
        search=search,
        counts=counts,
    )


@bp.route("/<int:deployment_id>")
@login_required
def detail(deployment_id):
    deployment = db.get_or_404(Deployment, deployment_id)
    return render_template(
        "deployments/detail.html",
        deployment=deployment,
        stages=deployment.stages(),
        previous_stable=deployment.previous_stable(),
    )
