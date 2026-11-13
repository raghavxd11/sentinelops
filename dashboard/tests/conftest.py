"""Shared pytest fixtures. Every test gets a fresh, empty database.

By default that is in-memory SQLite. To run the same tests against MySQL, set
TEST_DATABASE_URL to an empty database that is used only for tests (every
table in it is dropped after each test).
"""
import os

import pytest

from app import create_app
from app.extensions import db
from app.models import Service, User

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite://")
API_TOKEN = "test-token"
PASSWORD = "correct-horse-battery"


@pytest.fixture
def app():
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": TEST_DATABASE_URL,
            "WTF_CSRF_ENABLED": False,  # CSRF itself is tested in test_security.py
            "API_TOKEN": API_TOKEN,
        }
    )
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user(app):
    user = User(username="raghav", email="raghav@example.com")
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def auth_client(client, user):
    """A test client that is already logged in."""
    client.post("/login", data={"username": user.username, "password": PASSWORD})
    return client


@pytest.fixture
def service(app):
    service = Service(
        name="demo-app",
        description="Production container",
        repo_url="https://github.com/raghavxd11/sentinelops",
        health_url="http://localhost:8000/health",
    )
    db.session.add(service)
    db.session.commit()
    return service


@pytest.fixture
def report(client, service):
    """Report a deployment the way Jenkins does. Returns the response."""

    def send(**overrides):
        payload = {
            "service": "demo-app",
            "commit_hash": "7c1e4b9d2f0a8e6b5c3d1f4a9b8e7d6c5b4a3f21",
            "commit_author": "Raghav Pandey",
            "commit_message": "feat: add /api/info endpoint",
            "branch": "main",
            "build_number": 48,
            "image_tag": "7c1e4b9",
            "status": "SUCCESS",
            "duration_seconds": 162,
        }
        payload.update(overrides)
        return client.post("/api/deployments", json=payload, headers={"X-API-Token": API_TOKEN})

    return send
