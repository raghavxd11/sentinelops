"""DevOps metrics are computed from known rows, so the expected numbers are exact."""
from datetime import timedelta

from app.extensions import db
from app.metrics import compute_stats, deployments_per_day
from app.models import Deployment, Incident, utcnow


def add_deployment(service, status, age=timedelta(hours=1), lead=None):
    created = utcnow() - age
    deployment = Deployment(
        service_id=service.id,
        commit_hash="c" * 40,
        status=status,
        created_at=created,
        committed_at=created - lead if lead else None,
    )
    db.session.add(deployment)
    return deployment


def test_empty_database(app):
    stats = compute_stats()
    assert stats["total_deployments"] == 0
    assert stats["success_rate"] is None
    assert stats["mttr_seconds"] is None
    assert stats["lead_time_seconds"] is None


def test_counts_and_success_rate(service):
    for status in ("SUCCESS", "SUCCESS", "SUCCESS", "FAILED", "ROLLED_BACK", "IN_PROGRESS"):
        add_deployment(service, status)
    db.session.commit()

    stats = compute_stats()
    assert stats["total_deployments"] == 6
    assert stats["rollbacks"] == 1
    assert stats["failed"] == 1
    # 3 of the 5 finished deployments succeeded; the running one is not counted.
    assert stats["success_rate"] == 60.0
    assert stats["status_breakdown"] == {
        "SUCCESS": 3, "FAILED": 1, "ROLLED_BACK": 1, "IN_PROGRESS": 1,
    }


def test_deployment_frequency_and_weekly_windows(service):
    for _ in range(7):
        add_deployment(service, "SUCCESS", age=timedelta(days=2))
    add_deployment(service, "FAILED", age=timedelta(days=10))
    db.session.commit()

    stats = compute_stats()
    assert stats["deployment_frequency_per_day"] == 1.0
    assert stats["last_7_days"]["deployments"] == 7
    assert stats["previous_7_days"]["deployments"] == 1
    assert stats["previous_7_days"]["success_rate"] == 0.0


def test_mttr_is_mean_of_resolved_incidents(service):
    opened = utcnow() - timedelta(hours=5)
    for minutes in (10, 30):
        db.session.add(
            Incident(
                service_id=service.id,
                title="resolved",
                status="RESOLVED",
                created_at=opened,
                resolved_at=opened + timedelta(minutes=minutes),
            )
        )
    db.session.add(Incident(service_id=service.id, title="still open", severity="CRITICAL"))
    db.session.commit()

    stats = compute_stats()
    assert stats["mttr_seconds"] == 20 * 60
    assert stats["resolved_incidents"] == 2
    assert stats["open_incidents"] == 1
    assert stats["open_incidents_high"] == 1


def test_lead_time_uses_successful_deployments_with_commit_time(service):
    add_deployment(service, "SUCCESS", lead=timedelta(minutes=4))
    add_deployment(service, "SUCCESS", lead=timedelta(minutes=8))
    add_deployment(service, "SUCCESS")  # no commit time reported: ignored
    add_deployment(service, "FAILED", lead=timedelta(minutes=60))  # never deployed: ignored
    db.session.commit()

    stats = compute_stats()
    assert stats["lead_time_seconds"] == 6 * 60
    assert stats["lead_time_samples"] == 2


def test_deployments_per_day_buckets(service):
    add_deployment(service, "SUCCESS", age=timedelta(0))
    add_deployment(service, "SUCCESS", age=timedelta(0))
    add_deployment(service, "FAILED", age=timedelta(days=3))
    add_deployment(service, "SUCCESS", age=timedelta(days=40))  # outside the window
    db.session.commit()

    chart = deployments_per_day(days=14)
    assert len(chart["labels"]) == 14
    assert chart["series"]["SUCCESS"][-1] == 2
    assert chart["series"]["FAILED"][-4] == 1
    assert sum(chart["series"]["SUCCESS"]) == 2


def test_api_stats_matches_compute_stats(client, service):
    add_deployment(service, "SUCCESS")
    db.session.commit()
    assert client.get("/api/stats").get_json() == compute_stats()
