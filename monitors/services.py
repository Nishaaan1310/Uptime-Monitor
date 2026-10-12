import uuid
from datetime import timedelta
from dataclasses import dataclass

from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from monitors.models import Monitor, CheckResult, Status
from monitors.checker import check_url, CheckOutcome, DEFAULT_TIMEOUT
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from math import ceil


@dataclass(frozen=True)
class MonitorReport:
    name: str
    status: str            # "up", "down", "error", "skipped", "lost"
    detail: str = ""


GRACE_SECONDS = 10
LEASE_MARGIN_SECONDS = 30

def worst_case_seconds(count, max_workers):
    rounds = ceil(count/ max_workers)
    return rounds * DEFAULT_TIMEOUT + GRACE_SECONDS


def save_monitor(monitor, outcome, started_at, token):
    with transaction.atomic():
        updated = Monitor.objects.filter(pk=monitor.pk, claim_token=token
        ).update(
            status=Status.UP if outcome.is_up else Status.DOWN,
            last_checked_at=started_at,
            next_check_at=started_at + timedelta(seconds=monitor.interval_seconds),
            claimed_until=None,
            claim_token=None,
        )
        if updated == 0:
            return False

        CheckResult.objects.create(
            monitor=monitor,
            is_up=outcome.is_up,
            status_code=outcome.status_code,
            response_time_ms=outcome.response_time_ms,
            error_message=outcome.error_message
        )

    return True

def fetch(url):
    #Runs in a worker thread. Network only: it must never touch the database.

    started_at = timezone.now()
    return started_at, check_url(url, timeout=DEFAULT_TIMEOUT)

def release_monitor(monitor, token):
    #Give a claimed monitor back. next_check_at is untouched, so it is due again at once.
    Monitor.objects.filter(pk=monitor.pk, claim_token=token).update(
        claimed_until=None, claim_token=None
    )

def describe(error):
    return f"{type(error).__name__}: {error}"

def lost_report(monitor):
    return MonitorReport(monitor.name, "lost", "claim expired and another run took over; result discarded")

def error_report(monitor, token, error):
    detail = describe(error)
    try:
        release_monitor(monitor, token)
    except Exception as release_error:
        detail += f"; could not release: {describe(release_error)}"
    return MonitorReport(monitor.name, "error", detail)

def finish(monitor, future, token):
    #Turn one finished future into a saved result and a report.
    try:
        started_at, outcome = future.result()
        saved = save_monitor(monitor, outcome, started_at, token)
    except Exception as e:
        return error_report(monitor, token, e)
    if not saved:
        return lost_report(monitor)
    return MonitorReport(monitor.name, "up" if outcome.is_up else "down", outcome.error_message)

def record_timeout(monitor, token):
    outcome = CheckOutcome(is_up=False, error_message="Timed out: the check did not finish in time")
    try:
        saved = save_monitor(monitor, outcome, timezone.now(), token)
    except Exception as e:
        return error_report(monitor, token, e)
    if not saved:
        return lost_report(monitor)
    return MonitorReport(monitor.name, "down", outcome.error_message)

def record_skipped(monitor, token):
    #The check never started: give the monitor back and report it as skipped.
    try:
        release_monitor(monitor, token)
    except Exception as e:
        return MonitorReport(
            monitor.name, "error",
            f"did not start before the dealine; could not release: {describe(e)}",
        )

    return MonitorReport(monitor.name, "skipped", "did not start before the deadline")


def claim_monitors(limit, now, lease, token):
    with transaction.atomic():
        due_monitors = list(
            Monitor.objects.select_for_update(skip_locked=True)
            .filter(is_active=True, next_check_at__lte=now)
            .filter(Q(claimed_until__isnull=True) | Q(claimed_until__lte=now))
            .order_by("next_check_at")[:limit]
        )
        if not due_monitors:
            return []

        Monitor.objects.filter(
            pk__in=[monitor.pk for monitor in due_monitors]
        ).update(claimed_until= now + lease, claim_token=token)

    return due_monitors

def run_due_checks(now=None, limit=100, max_workers=10, deadline_seconds=None):
    now = now or timezone.now()
    token = uuid.uuid4()

    longest_run = worst_case_seconds(limit, max_workers)
    if deadline_seconds is not None:
        longest_run = max(longest_run, deadline_seconds)
    lease = timedelta(seconds=longest_run + LEASE_MARGIN_SECONDS)

    monitors = claim_monitors(limit, now, lease, token)
    if not monitors:
        return []

    if deadline_seconds is None:
        deadline_seconds = worst_case_seconds(len(monitors), max_workers)

    reports = []
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        future_to_monitor = {executor.submit(fetch, monitor.url) : monitor for monitor in monitors }
        pending = set(future_to_monitor)

        try:
            for future in as_completed(future_to_monitor, timeout=deadline_seconds):
                pending.discard(future)
                reports.append(finish(future_to_monitor[future], future, token))
        except TimeoutError:
            pass # the deadline passed; whatever is left in `pending` is handled below

        for future in pending:
            monitor = future_to_monitor[future]
            if future.cancel():
                reports.append(record_skipped(monitor, token))

            elif future.done():
                reports.append(finish(monitor, future, token))
            else:
                reports.append(record_timeout(monitor, token))

    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return reports
