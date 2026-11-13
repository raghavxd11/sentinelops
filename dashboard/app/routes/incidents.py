"""Incidents: list, create, edit (root-cause note), mark resolved, delete."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from wtforms import SelectChoice

from ..extensions import db
from ..forms import IncidentForm
from ..models import Deployment, Incident, Service, utcnow

bp = Blueprint("incidents", __name__, url_prefix="/incidents")


def build_form(incident=None):
    """IncidentForm with its dropdowns filled from the database."""
    form = IncidentForm(obj=incident)
    form.service_id.choices = [
        SelectChoice(s.id, s.name) for s in Service.query.order_by(Service.name)
    ]

    recent = Deployment.query.order_by(Deployment.created_at.desc()).limit(50).all()
    # Keep the currently linked deployment selectable even if it is older than the last 50.
    if incident and incident.deployment and incident.deployment not in recent:
        recent.append(incident.deployment)
    form.deployment_id.choices = [SelectChoice(0, "None")] + [
        SelectChoice(d.id, f"{d.short_hash}  {d.service.name}  build #{d.build_number}  {d.status}")
        for d in recent
    ]
    return form


def save(incident, form):
    """Copy form data onto the incident. Returns False if the form has an error."""
    deployment = None
    if form.deployment_id.data:
        deployment = db.session.get(Deployment, form.deployment_id.data)
        if deployment is None or deployment.service_id != form.service_id.data:
            form.deployment_id.errors.append("That deployment belongs to a different service.")
            return False

    incident.title = form.title.data.strip()
    incident.service_id = form.service_id.data
    incident.deployment = deployment
    incident.severity = form.severity.data
    incident.root_cause = (form.root_cause.data or "").strip()
    return True


@bp.route("")
@login_required
def list_incidents():
    status = request.args.get("status", "OPEN")
    query = Incident.query
    if status in ("OPEN", "RESOLVED"):
        query = query.filter_by(status=status)
    else:
        status = "ALL"
    counts = {
        "OPEN": Incident.query.filter_by(status="OPEN").count(),
        "RESOLVED": Incident.query.filter_by(status="RESOLVED").count(),
    }
    counts["ALL"] = counts["OPEN"] + counts["RESOLVED"]
    incidents = query.order_by(Incident.created_at.desc()).all()
    return render_template(
        "incidents/list.html", incidents=incidents, status=status, counts=counts
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    if Service.query.count() == 0:
        flash("Add a service first. An incident always belongs to a service.", "info")
        return redirect(url_for("services.list_services"))

    form = build_form()
    if request.method == "GET" and request.args.get("deployment", type=int):
        # "Open incident" link on a deployment page pre-fills the form.
        deployment = db.session.get(Deployment, request.args.get("deployment", type=int))
        if deployment:
            form.deployment_id.data = deployment.id
            form.service_id.data = deployment.service_id

    if form.validate_on_submit():
        incident = Incident(status="OPEN")
        if save(incident, form):
            db.session.add(incident)
            db.session.commit()
            flash(f"Incident #{incident.id} opened.", "success")
            return redirect(url_for("incidents.list_incidents"))
    return render_template("incidents/form.html", form=form, incident=None)


@bp.route("/<int:incident_id>/edit", methods=["GET", "POST"])
@login_required
def edit(incident_id):
    incident = db.get_or_404(Incident, incident_id)
    form = build_form(incident)
    if request.method == "GET":
        form.deployment_id.data = incident.deployment_id or 0

    if form.validate_on_submit():
        if save(incident, form):
            db.session.commit()
            flash(f"Incident #{incident.id} updated.", "success")
            return redirect(url_for("incidents.list_incidents", status=incident.status))
    return render_template(
        "incidents/form.html",
        form=form,
        incident=incident,
        time_open_until=incident.resolved_at or utcnow(),
    )


@bp.route("/<int:incident_id>/resolve", methods=["POST"])
@login_required
def resolve(incident_id):
    incident = db.get_or_404(Incident, incident_id)
    if incident.status != "RESOLVED":
        incident.resolve()
        db.session.commit()
        flash(f"Incident #{incident.id} marked resolved.", "success")
    return redirect(request.referrer or url_for("incidents.list_incidents"))


@bp.route("/<int:incident_id>/delete", methods=["POST"])
@login_required
def delete(incident_id):
    incident = db.get_or_404(Incident, incident_id)
    db.session.delete(incident)
    db.session.commit()
    flash(f"Incident #{incident_id} deleted.", "success")
    return redirect(url_for("incidents.list_incidents"))
