import logging
import threading
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class BackendClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rsplit("/", 2)[0]
        self.count_events_url = base_url
        self.live_detections_url = f"{self.base_url}/live-detections"
        self.camera_config_url = f"{self.base_url}/camera-config"
        self.api_key = api_key

        self._live_sem = threading.Semaphore(3)
        self._count_sem = threading.Semaphore(10)
        self._lock = threading.Lock()
        self._stats = {
            "lastSuccessAt": None,
            "lastErrorAt": None,
            "lastError": None,
            "liveDropped": 0,
            "countDropped": 0,
            "liveInFlight": 0,
            "countInFlight": 0,
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

    def fetch_camera_config(self, camera_id: str) -> dict | None:
        try:
            resp = self._session.get(
                f"{self.camera_config_url}/{camera_id}",
                headers=self._default_headers,
                timeout=3,
            )
            if resp.status_code == 200:
                self._mark_success()
                return resp.json()

            self._mark_error(
                f"camera config HTTP {resp.status_code}: {resp.text[:200]}"
            )
            return None
        except requests.Timeout:
            self._mark_error("timeout fetching camera config")
            logger.warning("[BACKEND] Timeout ao buscar configuracao da camera %s", camera_id)
            return None
        except requests.ConnectionError:
            self._mark_error(f"connection error fetching camera config for {camera_id}")
            logger.warning("[BACKEND] Sem conexao ao buscar configuracao da camera %s", camera_id)
            return None
        except Exception as exc:
            self._mark_error(f"unexpected fetch_camera_config error: {exc}")
            logger.warning("[BACKEND] Erro ao buscar configuracao da camera %s: %s", camera_id, exc)
            return None

    def save_camera_config(
        self,
        camera_id: str,
        roi: dict,
        line: dict,
        count_direction: str,
    ) -> bool:
        payload = {
            "cameraId": camera_id,
            "roi": roi,
            "countLine": line,
            "countDirection": count_direction,
        }
        try:
            resp = self._session.post(
                f"{self.camera_config_url}/{camera_id}",
                json=payload,
                headers=self._default_headers,
                timeout=5,
            )
            if resp.status_code < 400:
                self._mark_success()
                return True

            self._mark_error(
                f"save camera config HTTP {resp.status_code}: {resp.text[:200]}"
            )
            logger.warning(
                "[BACKEND] Falha ao salvar configuracao da camera %s (HTTP %d)",
                camera_id,
                resp.status_code,
            )
            return False
        except requests.Timeout:
            self._mark_error(f"timeout saving camera config for {camera_id}")
            logger.warning("[BACKEND] Timeout ao salvar configuracao da camera %s", camera_id)
            return False
        except requests.ConnectionError:
            self._mark_error(f"connection error saving camera config for {camera_id}")
            logger.warning("[BACKEND] Sem conexao ao salvar configuracao da camera %s", camera_id)
            return False
        except Exception as exc:
            self._mark_error(f"unexpected save_camera_config error: {exc}")
            logger.warning("[BACKEND] Erro ao salvar configuracao da camera %s: %s", camera_id, exc)
            return False

    def send_count_event(self, payload: dict):
        if not self._count_sem.acquire(blocking=False):
            self._increment_stat("countDropped")
            logger.warning("[BACKEND] Count-event descartado por excesso de requisicoes pendentes")
            return

        self._increment_stat("countInFlight")
        thread = threading.Thread(
            target=self._post_with_release,
            args=(self.count_events_url, payload, self._count_sem, "countInFlight"),
            daemon=True,
        )
        thread.start()

    def send_live_detections(self, payload: dict):
        if not self._live_sem.acquire(blocking=False):
            self._increment_stat("liveDropped")
            return

        self._increment_stat("liveInFlight")
        thread = threading.Thread(
            target=self._post_with_release,
            args=(self.live_detections_url, payload, self._live_sem, "liveInFlight"),
            daemon=True,
        )
        thread.start()

    def get_health_snapshot(self) -> dict:
        with self._lock:
            return dict(self._stats)

    def _post_with_release(
        self,
        url: str,
        payload: dict,
        semaphore: threading.Semaphore,
        inflight_key: str,
    ):
        try:
            self._post(url, payload)
        finally:
            self._decrement_stat(inflight_key)
            semaphore.release()

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
