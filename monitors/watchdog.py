import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

def hard_exit():
    os._exit(1)

class Watchdog:
    #Ends the process if one run lasts longer than limit_seconds.

    def __init__(self, limit_seconds, on_timeout=hard_exit, check_every=1.0):
        self.limit_seconds = limit_seconds
        self.on_timeout = on_timeout
        self.check_every = check_every
        self._started = None
        self._stopped = threading.Event()
        threading.Thread(target=self._watch, daemon=True).start()

    def begin(self):
        self._started = time.monotonic()

    def end(self):
        self._started = None

    def stop(self):
        self._stopped.set()

    def _watch(self):
        while not self._stopped.wait(self.check_every):
            started = self._started
            if started is not None and time.monotonic() - started > self.limit_seconds:
                logger.critical(
                    "A run lasted over %s seconds; ending the process so it can be restarted",
                    self.limit_seconds,
                )
                self.on_timeout()
                return
