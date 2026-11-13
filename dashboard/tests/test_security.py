"""CSRF protection and error pages."""
import pytest

from app import create_app
from app.extensions import db
from app.models import Service, User


@pytest.fixture
def csrf_client():
    """An app with CSRF checks switched on, as in production."""
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "API_TOKEN": "test-token",
        }
    )
    with app.app_context():
        yield app.test_client()
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


def test_form_post_without_csrf_token_is_rejected(csrf_client):
    response = csrf_client.post(
        "/register",
        data={"username": "x-user", "email": "x@example.com", "password": "12345678",
              "confirm": "12345678"},
    )
    assert response.status_code == 400
    assert User.query.count() == 0


def test_delete_without_csrf_token_is_rejected(csrf_client):
    db.session.add(Service(name="demo-app"))
    db.session.commit()
    response = csrf_client.post("/services/1/delete")
    assert response.status_code == 400
    assert b"CSRF" in response.data
    assert Service.query.count() == 1


def test_login_form_contains_csrf_token(csrf_client):
    assert b'name="csrf_token"' in csrf_client.get("/login").data


def test_api_post_does_not_need_csrf_token(csrf_client):
    db.session.add(Service(name="demo-app"))
    db.session.commit()
    response = csrf_client.post(
        "/api/deployments",
        json={"service": "demo-app", "commit_hash": "a" * 40, "status": "SUCCESS"},
        headers={"X-API-Token": "test-token"},
    )
    assert response.status_code == 201


def test_404_page(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert b"Not found" in response.data
    assert b"sentinelops" in response.data


def test_500_page(app, client):
    @app.route("/boom")
    def boom():
        raise RuntimeError("deliberate test error")

    app.config["PROPAGATE_EXCEPTIONS"] = False
    response = client.get("/boom")
    assert response.status_code == 500
    assert b"Internal server error" in response.data
    assert b"deliberate test error" not in response.data  # no stack trace leaks to the page
