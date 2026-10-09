from datetime import timedelta
from dataclasses import dataclass

from django.utils import timezone
from django.db import transaction

from monitors.models import Monitor, CheckResult, Status
from monitors.checker import check_url, CheckOutcome, DEFAULT_TIMEOUT
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from math import ceil


@dataclass(frozen=True)
class MonitorReport:
    name: str
    status: str            # "up", "down" or "error", "skipped"
    detail: str = "" 


GRACE_SECONDS = 10


def save_monitor(monitor, outcome, started_at):
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

def fetch(url):
    """Runs in a worker thread. Network only: it must never touch the database."""

    started_at = timezone.now()
    return started_at, check_url(url, timeout=DEFAULT_TIMEOUT)

def describe(error):
    return f"{type(error).__name__}: {error}"

def finish(monitor, future):
    """Turn one finished future into a saved result and a report."""
    try:
        started_at, outcome = future.result()
        save_monitor(monitor, outcome, started_at)
    except Exception as e:
        return MonitorReport(monitor.name, "error", describe(e))
    return MonitorReport(monitor.name, "up" if outcome.is_up else "down", outcome.error_message)

def record_timeout(monitor):
    outcome = CheckOutcome(is_up=False, error_message="Timed out: the check did not finish in time")
    try:
        save_monitor(monitor, outcome, timezone.now())
    except Exception as e:
        return MonitorReport(monitor.name, "error", describe(e))
    return MonitorReport(monitor.name, "down", outcome.error_message)

def run_due_checks(now=None, limit=100, max_workers=10, deadline_seconds=None):
    now = now or timezone.now()
    monitors = list(
        Monitor.objects.filter(is_active=True, next_check_at__lte=now)
        .order_by("next_check_at")[:limit]
    )

    if not monitors:
        return []

    if deadline_seconds is None:
        rounds = ceil(len(monitors)/ max_workers)
        deadline_seconds = rounds * DEFAULT_TIMEOUT + GRACE_SECONDS

    reports = []
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        future_to_monitor = {executor.submit(fetch, monitor.url) : monitor for monitor in monitors }
        pending = set(future_to_monitor)

        try:
            for future in as_completed(future_to_monitor, timeout=deadline_seconds):
                pending.discard(future)
                reports.append(finish(future_to_monitor[future], future))
        except TimeoutError:
            pass # the deadline passed; whatever is left in `pending` is handled below

        for future in pending:
            monitor = future_to_monitor[future]
            if future.cancel():
                reports.append(MonitorReport(monitor.name, "skipped", "did not start before the deadline"))
            elif future.done():
                reports.append(finish(monitor, future))
            else:
                reports.append(record_timeout(monitor))

    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return reports
