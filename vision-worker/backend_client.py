import logging
import queue
import threading
import time
import hashlib

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class BackendClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        session_id: str = "",
        count_direction: str = "down_to_up",
        line_id: str = "main-line",
        count_queue_size: int = 64,
        live_queue_size: int = 4,
        count_worker_count: int = 2,
        live_worker_count: int = 1,
        start_workers: bool = True,
    ):
        # base_url is the crossing-events endpoint; derive host from it
        self.base_url = base_url.rsplit("/", 2)[0]
        self.count_events_url = base_url
        self.health_report_url = f"{self.base_url}/internal/health-report"
        self.api_key = api_key
        self.session_id = session_id
        self.count_direction = count_direction
        self.line_id = line_id

        self._previous_event_hash: str | None = None
        self._hash_lock = threading.Lock()

        self._count_queue = queue.Queue(maxsize=max(1, count_queue_size))
        self._live_queue = queue.Queue(maxsize=max(1, live_queue_size))
        self._lock = threading.Lock()
        self._stats = {
            "lastSuccessAt": None,
            "lastErrorAt": None,
            "lastError": None,
            "liveDropped": 0,
            "countDropped": 0,
            "liveInFlight": 0,
            "countInFlight": 0,
            "liveQueued": 0,
            "countQueued": 0,
        }

        self._session = requests.Session()
        retry = Retry(
            total=1,
            read=1,
            connect=1,
            backoff_factor=0.2,
            status_forcelist=[502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)
        self._default_headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }
        self._count_workers = []
        self._live_workers = []
        if start_workers:
            self._start_workers(max(1, count_worker_count), max(1, live_worker_count))

    # ── Stubs for removed endpoints ──────────────────────────────────────────
    # The new backend has no round or camera-config endpoints.
    # These stubs keep app.py running without modification.

    def fetch_current_round(self) -> dict | None:
        return None

    def fetch_camera_config(self, _camera_id: str) -> dict | None:
        return None

    def save_camera_config(
        self,
        _camera_id: str,
        _roi: dict,
        _line: dict,
        _count_direction: str,
    ) -> bool:
        return True

    # ── Active methods ────────────────────────────────────────────────────────

    def send_count_event(self, payload: dict):
        """
        Accepts the legacy payload from app.py and converts it to the new
        /internal/crossing-events schema before enqueuing.
        """
        if not self.session_id:
            logger.warning("[BACKEND] session_id nao configurado — evento de cruzamento ignorado")
            return

        timestamp_utc = payload.get("crossedAt", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        track_id = int(payload.get("trackId", 0))
        object_class = payload.get("vehicleType", "car")
        confidence = float(payload.get("confidence", 0.0))
        frame_number = int(payload.get("frameNumber", 0))

        event_hash = self._compute_hash(
            session_id=self.session_id,
            timestamp_utc=timestamp_utc,
            track_id=track_id,
            object_class=object_class,
            direction=self.count_direction,
            line_id=self.line_id,
            frame_number=frame_number,
            confidence=confidence,
        )

        new_payload = {
            "sessionId": self.session_id,
            "timestampUtc": timestamp_utc,
            "trackId": track_id,
            "objectClass": object_class,
            "direction": self.count_direction,
            "lineId": self.line_id,
            "confidence": confidence,
            "frameNumber": frame_number,
            "previousEventHash": self._previous_event_hash,
            "eventHash": event_hash,
        }

        with self._hash_lock:
            self._previous_event_hash = event_hash

        if self._enqueue_payload(
            self._count_queue,
            new_payload,
            dropped_key="countDropped",
            queued_key="countQueued",
            label="count-event",
            replace_oldest=False,
        ):
            logger.debug("[BACKEND] Count-event enfileirado")
        else:
            logger.warning("[BACKEND] Count-event descartado por fila cheia")

    def send_live_detections(self, payload: dict):
        # Live detection overlay is not used in the new backend (overlay is server-side).
        pass

    def send_health_report(self, report: dict):
        """POST /internal/health-report — opcional, chamado pelo vision worker."""
        if not self.session_id:
            return
        report["sessionId"] = self.session_id
        if self._enqueue_payload(
            self._live_queue,
            report,
            dropped_key="liveDropped",
            queued_key="liveQueued",
            label="health-report",
            replace_oldest=True,
        ):
            logger.debug("[BACKEND] Health report enfileirado")

    def get_health_snapshot(self) -> dict:
        with self._lock:
            return dict(self._stats)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _compute_hash(
        self,
        session_id: str,
        timestamp_utc: str,
        track_id: int,
        object_class: str,
        direction: str,
        line_id: str,
        frame_number: int,
        confidence: float,
    ) -> str:
        with self._hash_lock:
            previous = self._previous_event_hash or "GENESIS"

        raw = "|".join([
            session_id,
            timestamp_utc,
            str(track_id),
            object_class,
            direction,
            line_id,
            str(frame_number),
            f"{confidence:.4f}",
            previous,
        ])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _start_workers(self, count_worker_count: int, live_worker_count: int):
        for index in range(count_worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                args=(self._count_queue, self.count_events_url, "countInFlight", "countQueued"),
                name=f"backend-count-worker-{index + 1}",
                daemon=True,
            )
            worker.start()
            self._count_workers.append(worker)

        for index in range(live_worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                args=(self._live_queue, self.health_report_url, "liveInFlight", "liveQueued"),
                name=f"backend-health-worker-{index + 1}",
                daemon=True,
            )
            worker.start()
            self._live_workers.append(worker)

    def _worker_loop(
        self,
        payload_queue: queue.Queue,
        url: str,
        inflight_key: str,
        queued_key: str,
    ):
        while True:
            payload = payload_queue.get()
            self._decrement_stat(queued_key)
            self._increment_stat(inflight_key)
            try:
                self._post(url, payload)
            finally:
                self._decrement_stat(inflight_key)
                payload_queue.task_done()

    def _enqueue_payload(
        self,
        payload_queue: queue.Queue,
        payload: dict,
        *,
        dropped_key: str,
        queued_key: str,
        label: str,
        replace_oldest: bool,
    ) -> bool:
        try:
            payload_queue.put_nowait(payload)
            self._increment_stat(queued_key)
            return True
        except queue.Full:
            if replace_oldest:
                try:
                    payload_queue.get_nowait()
                    payload_queue.task_done()
                    self._decrement_stat(queued_key)
                    self._increment_stat(dropped_key)
                    logger.debug("[BACKEND] %s mais antigo descartado", label)
                except queue.Empty:
                    pass
                try:
                    payload_queue.put_nowait(payload)
                    self._increment_stat(queued_key)
                    return True
                except queue.Full:
                    pass

            self._increment_stat(dropped_key)
            return False

    def _post(self, url: str, payload: dict):
        try:
            resp = self._session.post(
                url,
                json=payload,
                headers=self._default_headers,
                timeout=5,
            )
            if resp.status_code >= 400:
                message = f"HTTP {resp.status_code}: {resp.text[:200]}"
                self._mark_error(message)
                logger.warning("[BACKEND] HTTP %d - %s", resp.status_code, resp.text[:200])
            else:
                self._mark_success()
                logger.debug("[BACKEND] Evento enviado (HTTP %d)", resp.status_code)
        except requests.ConnectionError:
            self._mark_error(f"connection error for {url}")
            logger.error("[BACKEND] Sem conexao com %s", url)
        except requests.Timeout:
            self._mark_error(f"timeout posting to {url}")
            logger.error("[BACKEND] Timeout ao enviar evento para %s", url)
        except Exception as exc:
            self._mark_error(f"unexpected post error: {exc}")
            logger.error("[BACKEND] Erro inesperado: %s", exc)

    def _mark_success(self):
        with self._lock:
            self._stats["lastSuccessAt"] = time.time()
            self._stats["lastError"] = None

    def _mark_error(self, message: str):
        with self._lock:
            self._stats["lastErrorAt"] = time.time()
            self._stats["lastError"] = message

    def _increment_stat(self, key: str):
        with self._lock:
            self._stats[key] += 1

    def _decrement_stat(self, key: str):
        with self._lock:
            self._stats[key] = max(0, self._stats[key] - 1)
