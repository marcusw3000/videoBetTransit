import hashlib
import logging
import queue
import threading
import time
from urllib.parse import quote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


def normalize_api_root(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    parsed = urlparse(raw)

    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"

    if "/internal/" in raw:
        return raw.split("/internal/", 1)[0]

    return raw


def normalize_crossing_events_url(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    if raw.endswith("/internal/crossing-events"):
        return raw
    if raw.endswith("/internal/round-count-event"):
        return f"{normalize_api_root(raw)}/internal/crossing-events"
    return f"{normalize_api_root(raw)}/internal/crossing-events"


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
        self.base_url = normalize_api_root(base_url)
        self.count_events_url = normalize_crossing_events_url(base_url)
        self.round_count_url = f"{self.base_url}/internal/round-count-event"
        self.current_round_url = f"{self.base_url}/rounds/current"
        self.profile_activation_url = f"{self.base_url}/internal/rounds/profile-activated"
        self.round_lock_url_template = f"{self.base_url}/internal/cameras/{{camera_id}}/round-lock"
        self.camera_config_validation_url = f"{self.base_url}/internal/camera-config/validate-change"
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

    def fetch_current_round(self, camera_id: str = "") -> dict | None:
        url = self.current_round_url
        normalized_camera_id = str(camera_id or "").strip()
        if normalized_camera_id:
            url = f"{url}?cameraId={quote(normalized_camera_id)}"

        try:
            resp = self._session.get(
                url,
                headers=self._default_headers,
                timeout=3,
            )
            if resp.status_code == 200:
                self._mark_success()
                return resp.json()

            self._mark_error(
                f"current round HTTP {resp.status_code}: {resp.text[:200]}"
            )
            return None
        except requests.Timeout:
            self._mark_error("timeout fetching current round")
            logger.warning("[BACKEND] Timeout ao buscar round atual")
            return None
        except requests.ConnectionError:
            self._mark_error("connection error fetching current round")
            logger.warning("[BACKEND] Sem conexao ao buscar round atual")
            return None
        except Exception as exc:
            self._mark_error(f"unexpected fetch_current_round error: {exc}")
            logger.warning("[BACKEND] Erro ao buscar round atual: %s", exc)
            return None

    def fetch_camera_config(self, _camera_id: str) -> dict | None:
        return None

    def fetch_round_lock(self, camera_id: str) -> dict | None:
        normalized_camera_id = str(camera_id or "").strip()
        if not normalized_camera_id:
            return {"cameraId": "", "isLocked": False, "reason": None}

        try:
            resp = self._session.get(
                self.round_lock_url_template.format(camera_id=quote(normalized_camera_id)),
                headers=self._default_headers,
                timeout=3,
            )
            if resp.status_code == 200:
                self._mark_success()
                return resp.json()

            self._mark_error(f"round lock HTTP {resp.status_code}: {resp.text[:200]}")
            logger.warning("[BACKEND] Falha ao consultar round lock (%s): %s", resp.status_code, resp.text[:200])
            return None
        except requests.Timeout:
            self._mark_error("timeout fetching round lock")
            logger.warning("[BACKEND] Timeout ao consultar round lock")
            return None
        except requests.ConnectionError:
            self._mark_error("connection error fetching round lock")
            logger.warning("[BACKEND] Sem conexao ao consultar round lock")
            return None
        except Exception as exc:
            self._mark_error(f"unexpected round lock error: {exc}")
            logger.warning("[BACKEND] Erro ao consultar round lock: %s", exc)
            return None

    def ensure_camera_unlocked(self, camera_id: str, operation_name: str = "operacao") -> tuple[bool, str]:
        lock_state = self.fetch_round_lock(camera_id)
        if lock_state is None:
            return False, "Nao foi possivel validar o bloqueio operacional no backend."

        if bool(lock_state.get("isLocked")):
            return False, str(lock_state.get("reason") or "Camera locked while round is active; try again after settlement.")

        return True, ""

    def notify_stream_profile_activated(
        self,
        camera_id: str,
        stream_profile_id: str = "",
        *,
        allow_settling: bool = False,
    ) -> bool:
        payload = {
            "cameraId": str(camera_id or "").strip(),
            "streamProfileId": str(stream_profile_id or "").strip(),
            "allowSettling": bool(allow_settling),
        }

        if not payload["cameraId"]:
            return False

        try:
            resp = self._session.post(
                self.profile_activation_url,
                json=payload,
                headers=self._default_headers,
                timeout=5,
            )
            if resp.status_code >= 400:
                self._mark_error(f"profile activation HTTP {resp.status_code}: {resp.text[:200]}")
                logger.warning("[BACKEND] Falha ao notificar stream profile (%s): %s", resp.status_code, resp.text[:200])
                return False

            self._mark_success()
            return True
        except requests.ConnectionError:
            self._mark_error("connection error notifying stream profile activation")
            logger.error("[BACKEND] Sem conexao ao notificar stream profile")
            return False
        except requests.Timeout:
            self._mark_error("timeout notifying stream profile activation")
            logger.error("[BACKEND] Timeout ao notificar stream profile")
            return False
        except Exception as exc:
            self._mark_error(f"unexpected profile activation error: {exc}")
            logger.error("[BACKEND] Erro ao notificar stream profile: %s", exc)
            return False

    def save_camera_config(
        self,
        camera_id: str,
        _roi: dict,
        _line: dict,
        _count_direction: str,
    ) -> bool:
        return self.validate_camera_config_change(camera_id)

    def ensure_camera_change_allowed(
        self,
        camera_id: str,
        operation_name: str = "operacao",
        *,
        allow_settling: bool = False,
    ) -> tuple[bool, str]:
        if not str(camera_id or "").strip():
            return False, f"Camera ID vazio para {operation_name}."

        ok = self.validate_camera_config_change(camera_id, allow_settling=allow_settling)
        if ok:
            return True, ""

        return False, "Nao foi possivel validar a janela operacional no backend."

    def validate_camera_config_change(
        self,
        camera_id: str,
        *,
        allow_settling: bool = False,
    ) -> bool:
        payload = {
            "cameraId": str(camera_id or "").strip(),
            "allowSettling": bool(allow_settling),
        }

        if not payload["cameraId"]:
            return False

        try:
            resp = self._session.post(
                self.camera_config_validation_url,
                json=payload,
                headers=self._default_headers,
                timeout=5,
            )
            if resp.status_code >= 400:
                self._mark_error(f"camera config validation HTTP {resp.status_code}: {resp.text[:200]}")
                logger.warning("[BACKEND] Falha ao validar camera config (%s): %s", resp.status_code, resp.text[:200])
                return False

            self._mark_success()
            return True
        except requests.ConnectionError:
            self._mark_error("connection error validating camera config")
            logger.error("[BACKEND] Sem conexao ao validar camera config")
            return False
        except requests.Timeout:
            self._mark_error("timeout validating camera config")
            logger.error("[BACKEND] Timeout ao validar camera config")
            return False
        except Exception as exc:
            self._mark_error(f"unexpected camera config validation error: {exc}")
            logger.error("[BACKEND] Erro ao validar camera config: %s", exc)
            return False

    def send_count_event(self, payload: dict):
        if not self.session_id:
            round_payload = {
                "cameraId": payload.get("cameraId", ""),
                "roundId": payload.get("roundId", ""),
                "streamProfileId": payload.get("streamProfileId", ""),
                "trackId": str(payload.get("trackId", "")),
                "vehicleType": payload.get("vehicleType", "car"),
                "direction": payload.get("direction", "unknown"),
                "lineId": payload.get("lineId", self.line_id),
                "confidence": float(payload.get("confidence", 1.0) or 1.0),
                "frameNumber": int(payload.get("frameNumber", 0) or 0),
                "crossedAt": payload.get(
                    "crossedAt",
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                ),
                "snapshotUrl": payload.get("snapshotUrl", ""),
                "source": payload.get("source", "vision_worker_round_count"),
                "previousEventHash": payload.get("previousEventHash", ""),
                "eventHash": payload.get("eventHash", ""),
                "countBefore": payload.get("countBefore"),
                "countAfter": payload.get("countAfter"),
                "totalCount": int(payload.get("totalCount", 0) or 0),
            }
            if self._enqueue_payload(
                self._count_queue,
                round_payload,
                dropped_key="countDropped",
                queued_key="countQueued",
                label="round-count-event",
                replace_oldest=False,
                target_url=self.round_count_url,
            ):
                logger.debug("[BACKEND] Round-count-event enfileirado")
            else:
                logger.warning("[BACKEND] Round-count-event descartado por fila cheia")
            return

        timestamp_utc = payload.get(
            "crossedAt",
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
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
            target_url=self.count_events_url,
        ):
            logger.debug("[BACKEND] Count-event enfileirado")
        else:
            logger.warning("[BACKEND] Count-event descartado por fila cheia")

    def send_live_detections(self, payload: dict):
        del payload

    def send_health_report(self, report: dict):
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
            target_url=self.health_report_url,
        ):
            logger.debug("[BACKEND] Health report enfileirado")

    def get_health_snapshot(self) -> dict:
        with self._lock:
            return dict(self._stats)

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
                args=(self._count_queue, "countInFlight", "countQueued"),
                name=f"backend-count-worker-{index + 1}",
                daemon=True,
            )
            worker.start()
            self._count_workers.append(worker)

        for index in range(live_worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                args=(self._live_queue, "liveInFlight", "liveQueued"),
                name=f"backend-health-worker-{index + 1}",
                daemon=True,
            )
            worker.start()
            self._live_workers.append(worker)

    def _worker_loop(
        self,
        payload_queue: queue.Queue,
        inflight_key: str,
        queued_key: str,
    ):
        while True:
            job = payload_queue.get()
            self._decrement_stat(queued_key)
            self._increment_stat(inflight_key)
            try:
                self._post(job["url"], job["payload"])
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
        target_url: str,
    ) -> bool:
        job = {
            "url": target_url,
            "payload": payload,
        }
        try:
            payload_queue.put_nowait(job)
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
                    payload_queue.put_nowait(job)
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
