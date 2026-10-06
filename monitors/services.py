from datetime import timedelta
from dataclasses import dataclass

from django.utils import timezone
from django.db import transaction

from monitors.models import Monitor, CheckResult, Status
from monitors.checker import check_url

@dataclass(frozen=True)
class MonitorReport:
    name: str
    status: str            # "up", "down" or "error"
    detail: str = "" 


def check_monitor(monitor, started_at):
    outcome = check_url(monitor.url)

    with transaction.atomic():
        CheckResult.objects.create(
            monitor=monitor,
            is_up=outcome.is_up,
            status_code=outcome.status_code,
            response_time_ms=outcome.response_time_ms,
            error_message=outcome.error_message
        )

        monitor.status = Status.UP if outcome.is_up else Status.DOWN
        monitor.last_checked_at = started_at
        monitor.next_check_at = started_at + timedelta(seconds=monitor.interval_seconds)
        monitor.save(update_fields=["status", "last_checked_at", "next_check_at"])

    return outcome
    

def run_due_checks(now=None, limit=100):
    now = now or timezone.now()

    due_monitors = (
        Monitor.objects.filter(is_active=True, next_check_at__lte=now)
        .order_by("next_check_at")[:limit]
    )

    reports = []

    for monitor in due_monitors:
        started_at = timezone.now()
        try:
            outcome = check_monitor(monitor, started_at)
        except Exception as e:
            reports.append(MonitorReport(monitor.name, "error", str(e)))
            continue

        reports.append(MonitorReport(monitor.name, "up" if outcome.is_up else "down"))

    return reports

