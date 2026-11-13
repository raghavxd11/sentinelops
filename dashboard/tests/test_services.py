"""Services CRUD."""
from app.extensions import db
from app.models import Deployment, Incident, Service


def test_list_shows_services(auth_client, service):
    response = auth_client.get("/services")
    assert response.status_code == 200
    assert b"demo-app" in response.data


def test_empty_state(auth_client):
    assert b"No services yet." in auth_client.get("/services").data


def test_create(auth_client):
    response = auth_client.post(
        "/services/new",
        data={
            "name": "billing-api",
            "description": "Invoices",
            "repo_url": "https://github.com/example/billing",
            "health_url": "http://localhost:9000/health",
        },
    )
    assert response.status_code == 302
    created = Service.query.filter_by(name="billing-api").one()
    assert created.health_url == "http://localhost:9000/health"


def test_create_rejects_duplicate_name(auth_client, service):
    response = auth_client.post("/services/new", data={"name": "demo-app"})
    assert response.status_code == 400
    assert b"A service with this name already exists." in response.data
    assert Service.query.count() == 1


def test_create_rejects_invalid_name_and_url(auth_client):
    response = auth_client.post(
        "/services/new", data={"name": "Has Spaces", "health_url": "not-a-url"}
    )
    assert response.status_code == 400
    assert b"Lowercase letters, numbers and dashes only." in response.data
    assert b"Invalid URL." in response.data
    assert Service.query.count() == 0


def test_edit(auth_client, service):
    response = auth_client.post(
        f"/services/{service.id}/edit",
        data={"name": "demo-app", "description": "Updated description"},
    )
    assert response.status_code == 302
    assert db.session.get(Service, service.id).description == "Updated description"


def test_delete_cascades_to_deployments_and_incidents(auth_client, service, report):
    report(status="ROLLED_BACK")
    assert Deployment.query.count() == 1
    assert Incident.query.count() == 1

    response = auth_client.post(f"/services/{service.id}/delete")
    assert response.status_code == 302
    assert Service.query.count() == 0
    assert Deployment.query.count() == 0
    assert Incident.query.count() == 0


def test_edit_unknown_service_is_404(auth_client):
    assert auth_client.post("/services/999/edit", data={"name": "x"}).status_code == 404
