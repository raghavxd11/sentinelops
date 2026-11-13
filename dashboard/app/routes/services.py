"""Services: list, create, edit, delete (full CRUD)."""
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import login_required

from ..extensions import db
from ..forms import ServiceForm
from ..models import Service

bp = Blueprint("services", __name__, url_prefix="/services")


def render_list(form=None, modal_action=None, modal_title="Add service"):
    """Render the table. If a form with errors is passed, the modal reopens showing them."""
    services = Service.query.order_by(Service.name).all()
    return render_template(
        "services/list.html",
        services=services,
        form=form or ServiceForm(formdata=None),
        show_modal=form is not None,
        modal_action=modal_action or url_for("services.create"),
        modal_title=modal_title,
    )


def name_taken(name, ignore_id=None):
    existing = Service.query.filter_by(name=name).first()
    return existing is not None and existing.id != ignore_id


@bp.route("")
@login_required
def list_services():
    return render_list()


@bp.route("/new", methods=["POST"])
@login_required
def create():
    form = ServiceForm()
    if form.validate_on_submit():
        if name_taken(form.name.data):
            form.name.errors.append("A service with this name already exists.")
        else:
            service = Service(
                name=form.name.data,
                description=form.description.data or "",
                repo_url=form.repo_url.data or "",
                health_url=form.health_url.data or "",
            )
            db.session.add(service)
            db.session.commit()
            flash(f"Service {service.name} added.", "success")
            return redirect(url_for("services.list_services"))
    return render_list(form), 400


@bp.route("/<int:service_id>/edit", methods=["POST"])
@login_required
def edit(service_id):
    service = db.get_or_404(Service, service_id)
    form = ServiceForm()
    if form.validate_on_submit():
        if name_taken(form.name.data, ignore_id=service.id):
            form.name.errors.append("A service with this name already exists.")
        else:
            service.name = form.name.data
            service.description = form.description.data or ""
            service.repo_url = form.repo_url.data or ""
            service.health_url = form.health_url.data or ""
            db.session.commit()
            flash(f"Service {service.name} updated.", "success")
            return redirect(url_for("services.list_services"))
    action = url_for("services.edit", service_id=service.id)
    return render_list(form, modal_action=action, modal_title="Edit service"), 400


@bp.route("/<int:service_id>/delete", methods=["POST"])
@login_required
def delete(service_id):
    service = db.get_or_404(Service, service_id)
    name = service.name
    db.session.delete(service)  # cascades to its deployments and incidents
    db.session.commit()
    flash(f"Service {name} deleted.", "success")
    return redirect(url_for("services.list_services"))
