"""Every logged-in page renders, with and without data, and seed.py behaves."""
import seed
from app.extensions import db
from app.models import Deployment, Incident, Service, User

PAGES = (
    "/overview", "/services", "/deployments", "/incidents", "/incidents?status=ALL", "/api-docs",
)


def test_pages_render_on_empty_database(auth_client):
    for path in PAGES:
        assert auth_client.get(path).status_code == 200, path
    assert b"No deployments recorded yet." in auth_client.get("/overview").data


def test_pages_render_with_seed_data(auth_client):
    seed.seed()
    for path in PAGES:
        assert auth_client.get(path).status_code == 200, path

    for deployment in Deployment.query.all():
        assert auth_client.get(f"/deployments/{deployment.id}").status_code == 200
    incident = Incident.query.first()
    assert auth_client.get(f"/incidents/{incident.id}/edit").status_code == 200


def test_demo_data_note_only_shown_while_seed_rows_exist(auth_client):
    assert b"demo data" not in auth_client.get("/overview").data
    seed.seed()
    assert b"demo data" in auth_client.get("/overview").data
    seed.clear()
    assert b"demo data" not in auth_client.get("/overview").data


def test_seed_marks_every_row_and_creates_login(app):
    seed.seed()
    assert Deployment.query.count() > 20
    assert Deployment.query.filter_by(is_seed=False).count() == 0
    assert Incident.query.filter_by(is_seed=False).count() == 0
    assert Incident.query.filter_by(status="OPEN").count() == 2
    assert {s.name for s in Service.query} == {"demo-app", "demo-app-staging"}
    assert User.query.filter_by(username="admin").count() == 1


def test_seed_uses_only_the_repo_owner_as_author(app):
    seed.seed()
    authors = {deployment.commit_author for deployment in Deployment.query}
    assert authors == {"Raghav Pandey"}


def test_seed_twice_does_not_duplicate(app):
    seed.seed()
    first = Deployment.query.count()
    seed.seed()
    assert Deployment.query.count() == first
    assert Service.query.count() == 2


def test_clear_keeps_real_pipeline_data(app, report):
    seed.seed()
    report(status="FAILED", failed_stage="Test")  # a real report from Jenkins

    seed.clear()

    assert Deployment.query.count() == 1
    assert Incident.query.count() == 1
    assert Deployment.query.one().is_seed is False
    assert Service.query.count() == 2  # services are kept


def test_clear_unlinks_real_incident_from_seeded_deployment(app):
    seed.seed()
    seeded = Deployment.query.first()
    real = Incident(service_id=seeded.service_id, deployment_id=seeded.id, title="raised by hand")
    db.session.add(real)
    db.session.commit()

    seed.clear()

    kept = Incident.query.one()
    assert kept.title == "raised by hand"
    assert kept.deployment_id is None
