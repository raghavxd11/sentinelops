"""Register, login, logout and access control."""
from app.models import User
from tests.conftest import PASSWORD


def test_landing_page_is_public(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Self-healing CI/CD" in response.data


def test_protected_pages_redirect_to_login(client):
    for path in ("/overview", "/services", "/deployments", "/incidents", "/api-docs"):
        response = client.get(path)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


def test_register_creates_user_with_hashed_password(client):
    response = client.post(
        "/register",
        data={
            "username": "newuser",
            "email": "New@Example.com",
            "password": "a-long-password",
            "confirm": "a-long-password",
        },
    )
    assert response.status_code == 302

    user = User.query.filter_by(username="newuser").one()
    assert user.email == "new@example.com"
    assert user.password_hash != "a-long-password"
    assert user.check_password("a-long-password")


def test_register_rejects_duplicate_username(client, user):
    response = client.post(
        "/register",
        data={
            "username": user.username,
            "email": "other@example.com",
            "password": "a-long-password",
            "confirm": "a-long-password",
        },
    )
    assert response.status_code == 200
    assert b"That username is taken." in response.data
    assert User.query.count() == 1


def test_register_rejects_short_and_mismatched_password(client):
    response = client.post(
        "/register",
        data={"username": "newuser", "email": "n@example.com", "password": "short", "confirm": "x"},
    )
    assert b"Use at least 8 characters." in response.data
    assert b"Passwords do not match." in response.data
    assert User.query.count() == 0


def test_login_success_opens_overview(client, user):
    response = client.post(
        "/login", data={"username": user.username, "password": PASSWORD}, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Total deployments" in response.data


def test_login_wrong_password(client, user):
    response = client.post("/login", data={"username": user.username, "password": "wrong"})
    assert response.status_code == 200
    assert b"Wrong username or password." in response.data
    assert client.get("/overview").status_code == 302


def test_login_ignores_external_next_url(client, user):
    response = client.post(
        "/login?next=https://evil.example", data={"username": user.username, "password": PASSWORD}
    )
    assert response.headers["Location"] == "/overview"


def test_login_follows_local_next_url(client, user):
    response = client.post(
        "/login?next=/incidents", data={"username": user.username, "password": PASSWORD}
    )
    assert response.headers["Location"] == "/incidents"


def test_logout(auth_client):
    assert auth_client.get("/overview").status_code == 200
    auth_client.post("/logout")
    assert auth_client.get("/overview").status_code == 302


def test_logout_must_be_post(auth_client):
    assert auth_client.get("/logout").status_code == 405


def test_usernames_are_not_case_sensitive(client, user):
    taken = client.post(
        "/register",
        data={
            "username": user.username.upper(),
            "email": "other@example.com",
            "password": PASSWORD,
            "confirm": PASSWORD,
        },
    )
    assert b"That username is taken." in taken.data
    assert User.query.count() == 1

    login = client.post("/login", data={"username": user.username.upper(), "password": PASSWORD})
    assert login.status_code == 302
