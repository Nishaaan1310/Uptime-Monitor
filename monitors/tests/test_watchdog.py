import threading
from django.test import SimpleTestCase
from monitors.watchdog import Watchdog


class WatchdogTests(SimpleTestCase):
    def make(self, limit):
        fired = threading.Event()
        watchdog = Watchdog(limit, on_timeout=fired.set, check_every=0.02)
        self.addCleanup(watchdog.stop)
        return watchdog, fired

    def test_fires_when_a_run_lasts_too_long(self):
        watchdog, fired = self.make(0.1)
        watchdog.begin()
        self.assertTrue(fired.wait(timeout=2))

    def test_does_not_fire_when_the_run_ends_in_time(self):
        watchdog, fired = self.make(0.3)
        watchdog.begin()
        watchdog.end()
        self.assertFalse(fired.wait(timeout=0.6))

    def test_does_not_fire_between_runs(self):
        _, fired = self.make(0.1)
        self.assertFalse(fired.wait(timeout=0.4))