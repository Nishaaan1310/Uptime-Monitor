import logging
import signal
import threading
import time
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from monitors.services import run_due_checks, run_time_limit_seconds
from monitors.watchdog import Watchdog

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help: "Run due monitor checks every few seconds until stopped (Ctrl+C)."

    def add_arguments(self, parser):
        parser.add_argument("--tick", type=float, default=10.0, help="seconds between runs")
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--max-workers", type=int, default=10)

    def handle(self, *args, **options):
        stop = threading.Event()

        def request_stop(signum, frame):
            if stop.is_set():
                raise SystemExit(1)
            stop.set()

        signal.signal(signal.SIGINT, request_stop)
        signal.signal(signal.SIGTERM, request_stop)
        
        limit_seconds = run_time_limit_seconds(options["limit"], options["max_workers"])
        watchdog = Watchdog(limit_seconds)

        self.stdout.write(f"Monitor loop started (tick {options['tick']}s, run limit {limit_seconds:.0f}s), Ctrl+C to stop")
        
        try:
            next_tick = time.monotonic()
            while not stop.is_set():
                self.run_once(options, watchdog)

                next_tick += options["tick"]
                delay = next_tick - time.monotonic()
                if delay < 0:
                    next_tick = time.monotonic()
                    delay = 0
                stop.wait(delay)
        finally:
            watchdog.stop()

        self.stdout.write("Stopped.")

    def run_once(self, options, watchdog):
        watchdog.begin()
        try:
            close_old_connections()
            reports = run_due_checks(limit=options["limit"], max_workers=options["max_workers"])
        except Exception:
            logger.exception("Monitor run failed; will try again at the next tick")
            return
        finally:
            watchdog.end()

        if reports:
            counts = Counter(report.status for report in reports)
            summary = ", ".join(f"{n} {status}" for status, n in sorted(counts.items()))
            self.stdout.write(f"{timezone.now():%H:%M:%S} {summary}")


        