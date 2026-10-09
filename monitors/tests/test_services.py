import threading
import time
from unittest.mock import patch

from django.test import TestCase

from monitors.checker import CheckOutcome
from monitors.services import run_due_checks

import threading
import time
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from monitors import services
from monitors.checker import CheckOutcome
from monitors.models import Status
from monitors.services import MonitorReport, run_due_checks
from .helpers import make_monitor, make_user


def ok(url, timeout=10):
    return CheckOutcome(is_up=True, status_code=200, response_time_ms=5)


def patch_check(fake):
    """For the length of the block, check_url (as the services see it) is replaced by `fake`."""
    return patch("monitors.services.check_url", side_effect=fake)


def by_name(reports):
    return {report.name: report for report in reports}


class RunDueChecksTests(TestCase):
    def setUp(self):
        self.owner = make_user()

    def test_successful_checks_are_saved_and_rescheduled(self):
        a = make_monitor(self.owner, name="A")
        b = make_monitor(self.owner, name="B")
        old_due = a.next_check_at

        with patch_check(ok):
            reports = run_due_checks()

        self.assertEqual(sorted(r.status for r in reports), ["up", "up"])
        for monitor in (a, b):
            monitor.refresh_from_db()
            self.assertEqual(monitor.status, Status.UP)
            self.assertEqual(monitor.results.count(), 1)
            self.assertEqual(
                monitor.next_check_at,
                monitor.last_checked_at + timedelta(seconds=monitor.interval_seconds),
            )
        self.assertGreater(a.next_check_at, old_due)

    def test_a_down_result_is_saved_with_its_status_code(self):
        monitor = make_monitor(self.owner)

        def failing(url, timeout=10):
            return CheckOutcome(is_up=False, status_code=500, response_time_ms=7)

        with patch_check(failing):
            [report] = run_due_checks()

        self.assertEqual(report.status, "down")
        monitor.refresh_from_db()
        self.assertEqual(monitor.status, Status.DOWN)
        result = monitor.results.get()
        self.assertFalse(result.is_up)
        self.assertEqual(result.status_code, 500)

    def test_the_report_carries_the_reason_a_monitor_is_down(self):
        make_monitor(self.owner)

        def timed_out(url, timeout=10):
            return CheckOutcome(is_up=False, error_message="Timed out after 10s")

        with patch_check(timed_out):
            [report] = run_due_checks()

        self.assertEqual(report.detail, "Timed out after 10s")

    def test_a_crashing_check_is_an_error_and_the_others_still_save(self):
        good = make_monitor(self.owner, name="Good", url="https://good.example")
        bad = make_monitor(self.owner, name="Bad", url="https://bad.example")
        bad_due = bad.next_check_at

        def sometimes_crashes(url, timeout=10):
            if "bad" in url:
                raise RuntimeError("worker blew up")
            return ok(url)

        with patch_check(sometimes_crashes):
            reports = by_name(run_due_checks())

        self.assertEqual(reports["Good"].status, "up")
        self.assertEqual(reports["Bad"].status, "error")
        self.assertIn("RuntimeError", reports["Bad"].detail)

        bad.refresh_from_db()
        self.assertEqual(bad.results.count(), 0)
        self.assertEqual(bad.status, Status.PENDING)
        self.assertEqual(bad.next_check_at, bad_due)       # still due on the next run
        good.refresh_from_db()
        self.assertEqual(good.results.count(), 1)

    def test_a_failing_save_is_an_error_and_the_others_still_save(self):
        make_monitor(self.owner, name="Fine")
        broken = make_monitor(self.owner, name="Broken")
        real_save = services.save_monitor

        def flaky_save(monitor, outcome, started_at):
            if monitor.name == "Broken":
                raise RuntimeError("disk full")
            return real_save(monitor, outcome, started_at)

        with patch_check(ok), patch("monitors.services.save_monitor", side_effect=flaky_save):
            reports = by_name(run_due_checks())

        self.assertEqual(reports["Fine"].status, "up")
        self.assertEqual(reports["Broken"].status, "error")
        self.assertIn("disk full", reports["Broken"].detail)
        broken.refresh_from_db()
        self.assertEqual(broken.results.count(), 0)

    def test_every_due_monitor_gets_exactly_one_report(self):
        for name in ("Up", "Down", "Crash"):
            make_monitor(self.owner, name=name, url=f"https://{name.lower()}.example")

        def mixed(url, timeout=10):
            if "down" in url:
                return CheckOutcome(is_up=False, status_code=503, response_time_ms=3)
            if "crash" in url:
                raise RuntimeError("boom")
            return ok(url)

        with patch_check(mixed):
            reports = run_due_checks()

        self.assertEqual(len(reports), 3)
        self.assertEqual(sorted(r.status for r in reports), ["down", "error", "up"])


class SelectionTests(TestCase):
    def setUp(self):
        self.owner = make_user()

    def test_paused_and_not_yet_due_monitors_are_ignored(self):
        make_monitor(self.owner, name="Paused", is_active=False)
        make_monitor(self.owner, name="Later", next_check_at=timezone.now() + timedelta(hours=1))

        with patch_check(ok) as fake:
            reports = run_due_checks()

        self.assertEqual(reports, [])
        fake.assert_not_called()

    def test_limit_picks_the_most_overdue_first(self):
        now = timezone.now()
        for i, name in enumerate(["Oldest", "Middle", "Newest"]):
            make_monitor(self.owner, name=name, next_check_at=now - timedelta(minutes=10 - i))

        with patch_check(ok):
            reports = run_due_checks(limit=2)

        self.assertEqual({r.name for r in reports}, {"Oldest", "Middle"})


class StartTimeTests(TestCase):
    def test_each_monitor_records_when_its_own_check_started(self):
        owner = make_user()
        now = timezone.now()
        first = make_monitor(owner, name="First", next_check_at=now - timedelta(minutes=2))
        second = make_monitor(owner, name="Second", next_check_at=now - timedelta(minutes=1))

        def slowish(url, timeout=10):
            time.sleep(0.1)
            return ok(url)

        with patch_check(slowish):
            run_due_checks(max_workers=1)          # one worker: the second starts after the first ends

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertGreaterEqual(second.last_checked_at - first.last_checked_at, timedelta(milliseconds=90))


class DeadlineTests(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.release = threading.Event()
        self.addCleanup(self.release.set)          # never leave a worker thread stuck after a test

    def stuck_or_ok(self, url, timeout=10):
        if "slow" in url:
            self.release.wait(timeout=5)           # hangs until the test lets go (or 5 seconds pass)
        return ok(url)

    def test_a_stuck_check_is_recorded_down_once_and_does_not_hold_up_the_run(self):
        slow = make_monitor(self.owner, name="Slow", url="https://slow.example")
        make_monitor(self.owner, name="Fast", url="https://fast.example")

        started = time.monotonic()
        with patch_check(self.stuck_or_ok):
            reports = by_name(run_due_checks(deadline_seconds=0.3))
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 2)                # it did not wait for the stuck check
        self.assertEqual(reports["Fast"].status, "up")
        self.assertEqual(reports["Slow"].status, "down")
        self.assertIn("Timed out", reports["Slow"].detail)

        slow.refresh_from_db()
        self.assertEqual(slow.status, Status.DOWN)
        self.assertEqual(slow.results.count(), 1)

        self.release.set()                         # let the stuck check finish now
        time.sleep(0.3)
        self.assertEqual(slow.results.count(), 1)  # its late result was never written

    def test_a_check_that_never_started_is_skipped_and_stays_due(self):
        now = timezone.now()
        make_monitor(self.owner, name="Slow", url="https://slow.example",
                     next_check_at=now - timedelta(minutes=2))
        waiting = make_monitor(self.owner, name="Waiting", url="https://waiting.example",
                               next_check_at=now - timedelta(minutes=1))
        waiting_due = waiting.next_check_at

        with patch_check(self.stuck_or_ok):
            reports = by_name(run_due_checks(max_workers=1, deadline_seconds=0.3))

        self.assertEqual(reports["Slow"].status, "down")
        self.assertEqual(reports["Waiting"].status, "skipped")

        waiting.refresh_from_db()
        self.assertEqual(waiting.results.count(), 0)
        self.assertEqual(waiting.status, Status.PENDING)
        self.assertIsNone(waiting.last_checked_at)
        self.assertEqual(waiting.next_check_at, waiting_due)    # still due on the next run


class RunChecksCommandTests(SimpleTestCase):
    def run_command(self, reports):
        out, err = StringIO(), StringIO()
        with patch("monitors.management.commands.run_checks.run_due_checks", return_value=reports):
            call_command("run_checks", stdout=out, stderr=err, no_color=True)
        return out.getvalue(), err.getvalue()

    def test_prints_a_line_per_monitor_and_a_summary(self):
        out, err = self.run_command([
            MonitorReport("Blog", "up"),
            MonitorReport("API", "down", "Timed out after 10s"),
            MonitorReport("Shop", "skipped", "did not start before the deadline"),
            MonitorReport("Docs", "error", "boom"),
        ])
        self.assertIn("Blog: UP", out)
        self.assertIn("API: DOWN (Timed out after 10s)", out)
        self.assertIn("Shop: SKIPPED (did not start before the deadline)", out)
        self.assertIn("Docs: ERROR (boom)", err)
        self.assertNotIn("Docs", out)
        self.assertIn("Checked 2: 1 up, 1 down, 1 skipped, 1 errored", out)

    def test_nothing_due_still_prints_a_summary(self):
        out, err = self.run_command([])
        self.assertIn("Checked 0: 0 up, 0 down", out)
        self.assertEqual(err, "")