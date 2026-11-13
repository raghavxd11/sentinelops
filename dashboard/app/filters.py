"""Jinja template filters for formatting times, durations and labels."""
from .models import utcnow

STATUS_LABELS = {
    "SUCCESS": "Success",
    "FAILED": "Failed",
    "ROLLED_BACK": "Rolled back",
    "IN_PROGRESS": "In progress",
    "OPEN": "Open",
    "RESOLVED": "Resolved",
}


def timeago(value):
    """Datetime -> '3 min ago'."""
    if value is None:
        return "-"
    seconds = int((utcnow() - value).total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} hr ago"
    days = seconds // 86400
    if days < 30:
        return f"{days} day{'s' if days != 1 else ''} ago"
    return value.strftime("%d %b %Y")


def fulldate(value):
    if value is None:
        return ""
    return value.strftime("%d %b %Y, %H:%M:%S UTC")


def duration(seconds):
    """Seconds -> '42s', '2m 42s' or '1h 12m'."""
    if seconds is None:
        return "-"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60:02d}m"


def initials(name):
    """'Raghav Pandey' -> 'RP'."""
    parts = (name or "").split()
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def status_label(status):
    return STATUS_LABELS.get(status, status)


def status_class(status):
    """'ROLLED_BACK' -> 'rolled-back' (CSS class suffix)."""
    return (status or "").lower().replace("_", "-")


def register_filters(app):
    app.add_template_filter(timeago)
    app.add_template_filter(fulldate)
    app.add_template_filter(duration)
    app.add_template_filter(initials)
    app.add_template_filter(status_label)
    app.add_template_filter(status_class)
