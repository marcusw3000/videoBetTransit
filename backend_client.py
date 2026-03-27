import logging
import threading

import requests

logger = logging.getLogger(__name__)


class BackendClient:
    def __init__(self, base_url: str, api_key: str):
        # base_url example: "http://localhost:5000/api/rounds/count-events"
        # We derive the base from it
        self.base_url = base_url.rsplit("/", 2)[0]  # "http://localhost:5000/api"
        self.count_events_url = base_url
        self.live_detections_url = f"{self.base_url}/live-detections"
        self.camera_config_url = f"{self.base_url}/camera-config"
        self.api_key = api_key
        # Limita threads simultâneas de live-detections para evitar acúmulo
        self._live_sem = threading.Semaphore(3)

    def fetch_camera_config(self, camera_id: str) -> dict | None:
        """Busca config de câmera do backend (ROI, linha, direção)."""
        try:
            resp = requests.get(
                f"{self.camera_config_url}/{camera_id}",
                timeout=3
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:
            return None

    def send_count_event(self, payload: dict):
        """Envia evento de contagem em thread separada."""
        thread = threading.Thread(
            target=self._post,
            args=(self.count_events_url, payload),
            daemon=True
        )
        thread.start()

    def send_live_detections(self, payload: dict):
        """Envia frame de detecções em thread separada (máx. 3 simultâneas)."""
        if not self._live_sem.acquire(blocking=False):
            return  # descarta frame se já há 3 requisições pendentes
        thread = threading.Thread(
            target=self._post_live,
            args=(self.live_detections_url, payload),
            daemon=True
        )
        thread.start()

    def _post_live(self, url: str, payload: dict):
        try:
            self._post(url, payload)
        finally:
            self._live_sem.release()

    def _post(self, url: str, payload: dict):
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": self.api_key
                },
                timeout=5
            )
            if resp.status_code >= 400:
                logger.warning(
                    "[BACKEND] HTTP %d — %s", resp.status_code, resp.text[:200]
                )
            else:
                logger.debug("[BACKEND] Evento enviado (HTTP %d)", resp.status_code)
        except requests.ConnectionError:
            logger.error("[BACKEND] Sem conexão com %s", url)
        except requests.Timeout:
            logger.error("[BACKEND] Timeout ao enviar evento")
        except Exception as e:
            logger.error("[BACKEND] Erro inesperado: %s", e)
