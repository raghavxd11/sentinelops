"""Deployments list, filters, detail page and the pipeline timeline."""
from app.models import STAGES, Deployment


def test_list_and_status_filter(auth_client, report):
    report(commit_hash="a" * 40, status="SUCCESS", build_number=1)
    report(commit_hash="b" * 40, status="FAILED", build_number=2, failed_stage="Test")

    everything = auth_client.get("/deployments").data
    assert b"aaaaaaa" in everything and b"bbbbbbb" in everything

    failed_only = auth_client.get("/deployments?status=FAILED").data
    assert b"bbbbbbb" in failed_only
    assert b"aaaaaaa" not in failed_only


def test_search_by_message_and_hash(auth_client, report):
    report(commit_hash="a" * 40, commit_message="fix: healthcheck retries", build_number=1)
    report(commit_hash="b" * 40, commit_message="docs: update readme", build_number=2)

    by_message = auth_client.get("/deployments?q=healthcheck").data
    assert b"aaaaaaa" in by_message and b"bbbbbbb" not in by_message

    by_hash = auth_client.get("/deployments?q=bbbb").data
    assert b"bbbbbbb" in by_hash and b"aaaaaaa" not in by_hash


def test_detail_shows_full_trace(auth_client, report):
    deployment_id = report().get_json()["id"]
    page = auth_client.get(f"/deployments/{deployment_id}").data
    for expected in (
        b"7c1e4b9d2f0a8e6b5c3d1f4a9b8e7d6c5b4a3f21",  # full commit hash
        b"Raghav Pandey",
        b"feat: add /api/info endpoint",
        b"main",
        b"#48",
        b"2m 42s",
    ):
        assert expected in page


def test_detail_of_rollback_names_previous_stable_and_incident(auth_client, report):
    report(commit_hash="a" * 40, status="SUCCESS", build_number=1)
    rolled_back = report(commit_hash="b" * 40, status="ROLLED_BACK", build_number=2).get_json()

    page = auth_client.get(f"/deployments/{rolled_back['id']}").data
    assert b"Rolled back to" in page
    assert b"aaaaaaa" in page
    assert b"Health check failed on demo-app" in page


def test_detail_unknown_id_is_404(auth_client):
    assert auth_client.get("/deployments/999").status_code == 404


def test_stages_success():
    assert Deployment(status="SUCCESS").stages() == [(name, "passed") for name in STAGES]


def test_stages_rolled_back_fails_health_check_then_rolls_back():
    stages = Deployment(status="ROLLED_BACK").stages()
    assert stages[-2:] == [("Health check", "failed"), ("Rollback", "passed")]
    assert all(state == "passed" for _, state in stages[:-2])


def test_stages_failed_marks_later_stages_skipped():
    stages = dict(Deployment(status="FAILED", failed_stage="Scan").stages())
    assert stages["Build"] == "passed"
    assert stages["Scan"] == "failed"
    assert stages["Push"] == "skipped"
    assert stages["Deploy"] == "skipped"


def test_stages_failed_without_stage_is_unknown():
    stages = Deployment(status="FAILED").stages()
    assert all(state == "unknown" for _, state in stages)
