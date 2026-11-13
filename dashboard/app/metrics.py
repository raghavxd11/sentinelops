"""DevOps metrics, computed from the deployments and incidents tables.

Used by the Overview page and by GET /api/stats, so both always agree.
"""
from datetime import timedelta

from .models import DEPLOYMENT_STATUSES, Deployment, Incident, utcnow


def success_rate(deployments):
    """Percentage of finished deployments that succeeded (IN_PROGRESS is ignored)."""
    finished = [d for d in deployments if d.status != "IN_PROGRESS"]
    if not finished:
        return None
    succeeded = sum(1 for d in finished if d.status == "SUCCESS")
    return round(100 * succeeded / len(finished), 1)


def window_summary(deployments):
    return {
        "deployments": len(deployments),
        "success_rate": success_rate(deployments),
        "rollbacks": sum(1 for d in deployments if d.status == "ROLLED_BACK"),
    }


def mean(values):
    return round(sum(values) / len(values)) if values else None


def compute_stats():
    now = utcnow()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    deployments = Deployment.query.all()
    last_week = [d for d in deployments if d.created_at >= week_ago]
    week_before = [d for d in deployments if two_weeks_ago <= d.created_at < week_ago]

    breakdown = {status: 0 for status in DEPLOYMENT_STATUSES}
    for d in deployments:
        breakdown[d.status] = breakdown.get(d.status, 0) + 1

    # MTTR: mean time from an incident being opened to being resolved.
    resolved = Incident.query.filter(Incident.resolved_at.isnot(None)).all()
    recovery_times = [(i.resolved_at - i.created_at).total_seconds() for i in resolved]

    # Lead time: mean time from the commit to its successful deployment.
    lead_times = [
        (d.created_at - d.committed_at).total_seconds()
        for d in deployments
        if d.status == "SUCCESS" and d.committed_at and d.created_at >= d.committed_at
    ]

    open_incidents = Incident.query.filter_by(status="OPEN").all()

    return {
        "total_deployments": len(deployments),
        "success_rate": success_rate(deployments),
        "rollbacks": breakdown["ROLLED_BACK"],
        "failed": breakdown["FAILED"],
        "status_breakdown": breakdown,
        "open_incidents": len(open_incidents),
        "open_incidents_high": sum(
            1 for i in open_incidents if i.severity in ("HIGH", "CRITICAL")
        ),
        # Deployments per day over the last 7 days.
        "deployment_frequency_per_day": round(len(last_week) / 7, 1),
        "mttr_seconds": mean(recovery_times),
        "resolved_incidents": len(resolved),
        "lead_time_seconds": mean(lead_times),
        "lead_time_samples": len(lead_times),
        "last_7_days": window_summary(last_week),
        "previous_7_days": window_summary(week_before),
    }


def deployments_per_day(days=14):
    """Counts per day and status for the stacked bar chart (dates are UTC)."""
    today = utcnow().date()
    first_day = today - timedelta(days=days - 1)
    all_days = [first_day + timedelta(days=offset) for offset in range(days)]

    series = {status: [0] * days for status in DEPLOYMENT_STATUSES}
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    for d in Deployment.query.filter(Deployment.created_at >= start).all():
        position = (d.created_at.date() - first_day).days
        if 0 <= position < days and d.status in series:
            series[d.status][position] += 1

    return {
        "labels": [day.strftime("%d %b") for day in all_days],
        "series": series,
    }
