"""REST API: token check, validation, auto-incident logic."""
from app.models import Deployment, Incident
from tests.conftest import API_TOKEN

PAYLOAD = {"service": "demo-app", "commit_hash": "a" * 40, "status": "SUCCESS"}


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "database": "ok"}


def test_post_without_token_is_rejected(client, service):
    response = client.post("/api/deployments", json=PAYLOAD)
    assert response.status_code == 401
    assert Deployment.query.count() == 0


def test_post_with_wrong_token_is_rejected(client, service):
    response = client.post("/api/deployments", json=PAYLOAD, headers={"X-API-Token": "wrong"})
    assert response.status_code == 401
    assert Deployment.query.count() == 0


def test_post_is_rejected_when_server_has_no_token_configured(app, client, service):
    app.config["API_TOKEN"] = ""
    response = client.post("/api/deployments", json=PAYLOAD, headers={"X-API-Token": ""})
    assert response.status_code == 401


def test_post_success_creates_deployment_and_no_incident(report):
    response = report(status="SUCCESS")
    assert response.status_code == 201
    body = response.get_json()
    assert body["status"] == "SUCCESS"
    assert body["incident_id"] is None

    deployment = Deployment.query.one()
    assert deployment.service.name == "demo-app"
    assert deployment.build_number == 48
    assert deployment.is_seed is False
    assert Incident.query.count() == 0


def test_post_failed_opens_linked_incident(report):
    body = report(status="FAILED", failed_stage="Scan").get_json()

    incident = Incident.query.one()
    assert body["incident_id"] == incident.id
    assert incident.deployment_id == body["id"]
    assert incident.status == "OPEN"
    assert incident.severity == "MEDIUM"
    assert "Scan" in incident.title


def test_post_rolled_back_opens_high_severity_incident(report):
    report(status="ROLLED_BACK")
    incident = Incident.query.one()
    assert incident.severity == "HIGH"
    assert incident.status == "OPEN"
    assert "rolled back" in incident.title


def test_post_validation_errors(report):
    assert report(status="EXPLODED").status_code == 400
    assert report(commit_hash="").status_code == 400
    assert report(build_number="forty-eight").status_code == 400
    assert report(failed_stage="Lunch").status_code == 400
    assert report(committed_at="yesterday").status_code == 400
    assert Deployment.query.count() == 0


def test_post_body_must_be_json(client, service):
    response = client.post(
        "/api/deployments", data="not json", headers={"X-API-Token": API_TOKEN}
    )
    assert response.status_code == 400


def test_post_unknown_service_is_404(report):
    assert report(service="does-not-exist").status_code == 404


def test_post_stores_commit_time_in_utc(report):
    report(committed_at="2026-11-13T14:00:00+05:30")
    committed = Deployment.query.one().committed_at
    assert (committed.hour, committed.minute) == (8, 30)


def test_final_result_updates_in_progress_row(report):
    first = report(status="IN_PROGRESS", duration_seconds=None)
    assert first.status_code == 201

    final = report(status="ROLLED_BACK")
    assert final.status_code == 200
    assert final.get_json()["id"] == first.get_json()["id"]
    assert Deployment.query.count() == 1
    assert Deployment.query.one().status == "ROLLED_BACK"
    assert Incident.query.count() == 1


def test_get_deployments_lists_newest_first_and_filters(client, report):
    report(commit_hash="a" * 40, status="SUCCESS", build_number=1)
    report(commit_hash="b" * 40, status="FAILED", build_number=2)

    everything = client.get("/api/deployments").get_json()
    assert [d["build_number"] for d in everything] == [2, 1]

    failed = client.get("/api/deployments?status=FAILED").get_json()
    assert [d["commit_hash"] for d in failed] == ["b" * 40]

    assert client.get("/api/deployments?status=NOPE").status_code == 400
    assert len(client.get("/api/deployments?limit=1").get_json()) == 1


def test_unknown_api_path_returns_json_404(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.get_json() == {"error": "Not found"}
