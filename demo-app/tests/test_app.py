"""Tests for every demo-app endpoint, including the deliberately broken health check."""
import pytest

from app import app


@pytest.fixture
def client(monkeypatch):
    # Start every test from a clean environment, whatever the shell has set.
    for name in ("APP_VERSION", "GIT_COMMIT", "BREAK_HEALTH"):
        monkeypatch.delenv(name, raising=False)
    app.config["TESTING"] = True
    return app.test_client()


def test_index_shows_version_and_commit(client, monkeypatch):
    monkeypatch.setenv("APP_VERSION", "1.2.0")
    monkeypatch.setenv("GIT_COMMIT", "7c1e4b9")

    response = client.get("/")

    assert response.status_code == 200
    assert response.content_type.startswith("text/html")
    assert b"demo-app" in response.data
    assert b"1.2.0" in response.data
    assert b"7c1e4b9" in response.data


def test_index_escapes_environment_values(client, monkeypatch):
    monkeypatch.setenv("APP_VERSION", "<script>alert(1)</script>")
    assert b"<script>alert(1)</script>" not in client.get("/").data


def test_health_ok_by_default(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_health_fails_when_break_health_is_true(client, monkeypatch):
    monkeypatch.setenv("BREAK_HEALTH", "true")

    response = client.get("/health")

    assert response.status_code == 500
    assert response.get_json()["status"] == "unhealthy"


@pytest.mark.parametrize("value", ["TRUE", "True", " true "])
def test_break_health_ignores_case_and_spaces(client, monkeypatch, value):
    monkeypatch.setenv("BREAK_HEALTH", value)
    assert client.get("/health").status_code == 500


@pytest.mark.parametrize("value", ["false", "", "0", "no"])
def test_health_stays_ok_for_other_values(client, monkeypatch, value):
    monkeypatch.setenv("BREAK_HEALTH", value)
    assert client.get("/health").status_code == 200


def test_index_reports_failing_health(client, monkeypatch):
    assert b"failing" not in client.get("/").data
    monkeypatch.setenv("BREAK_HEALTH", "true")
    response = client.get("/")
    assert response.status_code == 200  # the page still loads, only /health fails
    assert b"failing" in response.data


def test_info_returns_version_and_commit_from_environment(client, monkeypatch):
    monkeypatch.setenv("APP_VERSION", "1.2.0")
    monkeypatch.setenv("GIT_COMMIT", "7c1e4b9d2f0a8e6b5c3d1f4a9b8e7d6c5b4a3f21")

    body = client.get("/api/info").get_json()

    assert body["app"] == "demo-app"
    assert body["version"] == "1.2.0"
    assert body["git_commit"] == "7c1e4b9d2f0a8e6b5c3d1f4a9b8e7d6c5b4a3f21"
    assert body["hostname"]


def test_info_defaults_when_environment_is_not_set(client):
    body = client.get("/api/info").get_json()
    assert body["version"] == "dev"
    assert body["git_commit"] == "unknown"


def test_unknown_path_is_404(client):
    assert client.get("/nope").status_code == 404
