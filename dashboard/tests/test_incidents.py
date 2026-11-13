"""Incidents CRUD and the resolve action."""
from app.extensions import db
from app.models import Incident, Service


def make_incident(service, **fields):
    incident = Incident(service_id=service.id, title="Disk full on build host", **fields)
    db.session.add(incident)
    db.session.commit()
    return incident


def test_create(auth_client, service):
    response = auth_client.post(
        "/incidents/new",
        data={
            "title": "Staging returns 502",
            "service_id": service.id,
            "deployment_id": 0,
            "severity": "HIGH",
            "root_cause": "",
        },
    )
    assert response.status_code == 302
    incident = Incident.query.one()
    assert incident.title == "Staging returns 502"
    assert incident.severity == "HIGH"
    assert incident.status == "OPEN"
    assert incident.deployment_id is None
    assert incident.is_seed is False


def test_create_requires_title(auth_client, service):
    response = auth_client.post(
        "/incidents/new",
        data={"title": "", "service_id": service.id, "deployment_id": 0, "severity": "LOW"},
    )
    assert response.status_code == 200
    assert b"This field is required." in response.data
    assert Incident.query.count() == 0


def test_create_without_services_redirects_to_services(auth_client):
    response = auth_client.get("/incidents/new")
    assert response.status_code == 302
    assert response.headers["Location"] == "/services"


def test_create_rejects_deployment_from_another_service(auth_client, service, report):
    deployment_id = report().get_json()["id"]
    other = Service(name="other-app")
    db.session.add(other)
    db.session.commit()

    response = auth_client.post(
        "/incidents/new",
        data={
            "title": "Mismatch",
            "service_id": other.id,
            "deployment_id": deployment_id,
            "severity": "LOW",
        },
    )
    assert b"That deployment belongs to a different service." in response.data
    assert Incident.query.count() == 0


def test_edit_saves_root_cause(auth_client, service):
    incident = make_incident(service)
    response = auth_client.post(
        f"/incidents/{incident.id}/edit",
        data={
            "title": incident.title,
            "service_id": service.id,
            "deployment_id": 0,
            "severity": "CRITICAL",
            "root_cause": "Old images were never pruned.",
        },
    )
    assert response.status_code == 302
    updated = db.session.get(Incident, incident.id)
    assert updated.root_cause == "Old images were never pruned."
    assert updated.severity == "CRITICAL"


def test_edit_page_renders(auth_client, service):
    incident = make_incident(service)
    page = auth_client.get(f"/incidents/{incident.id}/edit")
    assert page.status_code == 200
    assert b"Disk full on build host" in page.data


def test_mark_resolved_sets_status_and_time(auth_client, service):
    incident = make_incident(service)
    response = auth_client.post(f"/incidents/{incident.id}/resolve")
    assert response.status_code == 302

    resolved = db.session.get(Incident, incident.id)
    assert resolved.status == "RESOLVED"
    assert resolved.resolved_at is not None
    assert resolved.resolved_at >= resolved.created_at


def test_list_filters_open_and_resolved(auth_client, service):
    make_incident(service)
    done = Incident(service_id=service.id, title="Already fixed thing")
    done.resolve()
    db.session.add(done)
    db.session.commit()

    open_page = auth_client.get("/incidents").data  # default filter is OPEN
    assert b"Disk full on build host" in open_page
    assert b"Already fixed thing" not in open_page

    resolved_page = auth_client.get("/incidents?status=RESOLVED").data
    assert b"Already fixed thing" in resolved_page
    assert b"Disk full on build host" not in resolved_page


def test_delete(auth_client, service):
    incident = make_incident(service)
    response = auth_client.post(f"/incidents/{incident.id}/delete")
    assert response.status_code == 302
    assert Incident.query.count() == 0
