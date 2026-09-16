"""Single-flight reads: network I/O never runs on the UI/inference thread."""
import logging
import threading
import time

PENDING = object()


class BackgroundPoll:
    def __init__(self):
        self._lock = threading.Lock()
        self._busy = False
        self._result = PENDING
        self._context = None
        self._next_at = 0.0

    def poll(self, context, fetch, interval):
        with self._lock:
            result = self._result if self._context == context else PENDING
            self._result = PENDING
            if not self._busy and (self._context != context or time.monotonic() >= self._next_at):
                self._context = context
                self._busy = True
                threading.Thread(target=self._fetch, args=(fetch, interval), daemon=True).start()
            return result

    def _fetch(self, fetch, interval):
        try:
            result = fetch()
        except Exception:
            logging.getLogger(__name__).exception("Falha na consulta em segundo plano")
            result = None
        with self._lock:
            self._result = result
            self._next_at = time.monotonic() + interval
            self._busy = False
