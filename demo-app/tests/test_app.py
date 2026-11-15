"""Tests for every demo-app page and endpoint, including the deliberately broken health check."""
import pytest

import app as demo_app
from app import app


@pytest.fixture
def break_file(tmp_path, monkeypatch):
    """Point the break-health flag file at a temporary path (not created yet)."""
    path = tmp_path / "break-health"
    monkeypatch.setattr(demo_app, "BREAK_HEALTH_FILE", str(path))
    return path


@pytest.fixture
def client(monkeypatch, break_file):
    # Start every test from a clean environment, whatever the shell has set.
    for name in ("APP_VERSION", "GIT_COMMIT", "BREAK_HEALTH"):
        monkeypatch.delenv(name, raising=False)
    app.config["TESTING"] = True
    return app.test_client()


PAGES = ["/", "/menu", "/about"]


@pytest.mark.parametrize("path", PAGES)
def test_pages_load_as_html(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.content_type.startswith("text/html")
    assert b"Brewly" in response.data


@pytest.mark.parametrize("path", PAGES)
def test_footer_shows_version_short_commit_and_container(client, monkeypatch, path):
    monkeypatch.setenv("APP_VERSION", "build-42")
    monkeypatch.setenv("GIT_COMMIT", "7c1e4b9d2f0a8e6b5c3d1f4a9b8e7d6c5b4a3f21")

    page = client.get(path).get_data(as_text=True)

    hostname = demo_app.socket.gethostname()
    assert f"Version build-42 · commit 7c1e4b9 · container {hostname}" in page
    assert "7c1e4b9d" not in page  # only the short commit is shown


def test_footer_defaults_when_environment_is_not_set(client):
    page = client.get("/").get_data(as_text=True)
    assert "Version dev · commit unknown · container" in page


def test_pages_escape_environment_values(client, monkeypatch):
    monkeypatch.setenv("APP_VERSION", "<script>alert(1)</script>")
    for path in PAGES:
        assert b"<script>alert(1)</script>" not in client.get(path).data


@pytest.mark.parametrize("path", PAGES)
def test_every_page_links_to_every_page(client, path):
    page = client.get(path).get_data(as_text=True)
    for link in PAGES:
        assert f'href="{link}"' in page


@pytest.mark.parametrize("path, label", [("/", "Home"), ("/menu", "Menu"), ("/about", "About")])
def test_navigation_marks_the_current_page(client, path, label):
    page = client.get(path).get_data(as_text=True)
    assert f'href="{path}" aria-current="page">{label}</a>' in page
    assert page.count('aria-current="page"') == 1


def test_home_has_hero_and_highlights(client):
    page = client.get("/").get_data(as_text=True)
    assert "Coffee roasted on Tuesday" in page
    assert page.count("<article>") == 3


def test_menu_lists_every_item_with_its_price(client):
    page = client.get("/menu").get_data(as_text=True)
    for section in demo_app.MENU:
        assert section["section"] in page
        for item in section["items"]:
            assert item["name"] in page
            assert f"₹{item['price']}" in page


def test_menu_data_is_complete():
    for section in demo_app.MENU:
        assert section["items"], f"{section['section']} has no items"
        for item in section["items"]:
            assert item["name"]
            assert isinstance(item["price"], int) and item["price"] > 0


def test_about_has_visiting_info(client):
    page = client.get("/about").get_data(as_text=True)
    assert "Visit" in page
    assert "12 Second Cross Street" in page


def test_stylesheet_is_served(client):
    response = client.get("/static/style.css")
    assert response.status_code == 200
    assert response.content_type.startswith("text/css")
    response.close()


def test_pages_still_load_while_health_is_broken(client, monkeypatch):
    """Only /health fails during the rollback demo; the website itself keeps working."""
    monkeypatch.setenv("BREAK_HEALTH", "true")
    for path in PAGES:
        assert client.get(path).status_code == 200


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


def test_health_fails_while_break_file_exists(client, break_file):
    assert client.get("/health").status_code == 200

    break_file.touch()  # what "docker exec <container> touch /tmp/break-health" does
    response = client.get("/health")
    assert response.status_code == 500
    assert response.get_json()["status"] == "unhealthy"

    break_file.unlink()
    assert client.get("/health").status_code == 200


def test_startup_removes_break_file(client, break_file):
    """After autoheal restarts the container, the app must start healthy again."""
    break_file.touch()
    demo_app.clear_break_health_file()
    assert not break_file.exists()
    assert client.get("/health").status_code == 200


def test_startup_without_break_file_is_fine(break_file):
    demo_app.clear_break_health_file()  # must not fail when there is no file
    assert not break_file.exists()


def test_unknown_path_is_404(client):
    assert client.get("/nope").status_code == 404
