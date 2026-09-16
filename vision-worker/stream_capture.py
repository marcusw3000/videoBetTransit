from __future__ import annotations
import cv2
import threading
import time
import logging
from runtime_stats import RuntimeStats
from buffered_hls import BufferedHlsCapture
from capture_backend import open_ffmpeg_capture
logger = logging.getLogger(__name__)


def normalize_ffmpeg_capture_options(options) -> str:
    if isinstance(options, str):
        return options.strip()

    if isinstance(options, dict):
        parts = []
        for key, value in options.items():
            parts.append(f"{key};{value}")
        return "|".join(parts)

    return ""



class StreamCapture:
    MAX_FAILURES = 30
    SOURCE_OPEN_FAILOVER_THRESHOLD = 2
    LIVE_EDGE_DRAIN_SECONDS = 1.25
    LIVE_EDGE_MAX_FRAMES = 60
    LIVE_EDGE_SLOW_READ_MS = 120.0

    def __init__(
        self,
        url: str,
        stats: RuntimeStats | None = None,
        *,
        fallback_url: str = "",
        ffmpeg_options=None,
        buffer_size: int = 1,
        open_timeout_ms: int = 5000,
        read_timeout_ms: int = 5000,
        target_fps: float = 0.0,
        lazy_open: bool = False,
        buffered_hls: bool = False,
        refresh_url=None,
    ):
        self.url = str(url or "").strip()
        self.stats = stats
        self.cap: cv2.VideoCapture | None = None
        self._fail_count = 0
        self.ffmpeg_options = normalize_ffmpeg_capture_options(ffmpeg_options)
        self.buffer_size = max(1, int(buffer_size))
        self.open_timeout_ms = max(0, int(open_timeout_ms))
        self.read_timeout_ms = max(0, int(read_timeout_ms))
        self.target_fps = max(0.0, float(target_fps))
        self._effective_fps = 0.0
        self._reset_requested = False
        self._refresh_latest_requested = False
        self._state_lock = threading.Lock()
        self._last_frame_monotonic = 0.0
        self._read_started_monotonic = 0.0
        self._forced_interrupt_count = 0
        self._source_urls = self._build_source_url_candidates(self.url, fallback_url)
        self._source_index = 0
        self._source_open_failures = [0 for _ in self._source_urls]
        self.url = self._source_urls[self._source_index]
        self._pending_source_url = None
        self._buffered_hls = buffered_hls
        self._refresh_url = refresh_url
        if not lazy_open:
            self._connect()

    @staticmethod
    def _build_source_url_candidates(primary_url: str, fallback_url: str) -> list[str]:
        candidates: list[str] = []
        for candidate in (primary_url, fallback_url):
            normalized = str(candidate or "").strip()
            if normalized and normalized not in candidates:
                candidates.append(normalized)
        if not candidates:
            raise ValueError("Nenhuma URL de captura configurada.")
        return candidates

    def _advance_source(self, reason: str) -> bool:
        if len(self._source_urls) <= 1:
            return False
        next_index = (self._source_index + 1) % len(self._source_urls)
        if next_index == self._source_index:
            return False
        previous_url = self._source_urls[self._source_index]
        self._source_index = next_index
        self.url = self._source_urls[self._source_index]
        logger.warning(
            "Alternando fonte de captura: %s -> %s (%s)",
            previous_url,
            self.url,
            reason,
        )
        return True

    def _connect(self):
        if self.cap is not None:
            self.cap.release()

        attempts_remaining = len(self._source_urls)
        while attempts_remaining > 0:
            self.url = self._source_urls[self._source_index]
            logger.info("Conectando ao stream: %s", self.url)
            if self.ffmpeg_options and not self._buffered_hls:
                logger.info("FFmpeg capture options: %s", self.ffmpeg_options)
            # FFmpeg timeouts are open-only properties; set() after opening
            # silently leaves the default (potentially 30 second) read timeout.
            params = []
            if self.open_timeout_ms > 0:
                params.extend([cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.open_timeout_ms])
            if self.read_timeout_ms > 0:
                params.extend([cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.read_timeout_ms])
            if self._buffered_hls:
                logger.info("Captura HLS com prefetch limitado a 3 segmentos comprimidos.")
                self.cap = BufferedHlsCapture(self.url, refresh_url=self._refresh_url)
            else:
                self.cap = open_ffmpeg_capture(self.url, params, self.ffmpeg_options)
            try:
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)
            except Exception:
                pass
            self._fail_count = 0
            opened = bool(self.cap.isOpened())
            if self.stats is not None:
                self.stats.set_stream_status(opened, self._fail_count)
            reported_fps = 0.0
            try:
                reported_fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
            except Exception:
                reported_fps = 0.0

            if self.target_fps > 0:
                self._effective_fps = self.target_fps
            elif 1.0 <= reported_fps <= 120.0:
                self._effective_fps = reported_fps
            else:
                self._effective_fps = 15.0

            logger.info(
                "Pacing do stream: fps configurado=%.2f | fps detectado=%.2f | fps efetivo=%.2f",
                self.target_fps,
                reported_fps,
                self._effective_fps,
            )

            if opened:
                self._source_open_failures[self._source_index] = 0
                return

            self._source_open_failures[self._source_index] += 1
            logger.warning("Falha ao abrir stream na conexao inicial.")
            attempts_remaining -= 1
            should_failover = (
                len(self._source_urls) > 1
                and self._source_open_failures[self._source_index] >= self.SOURCE_OPEN_FAILOVER_THRESHOLD
            )
            if not should_failover or not self._advance_source("falha de abertura consecutiva"):
                return

        if self.stats is not None:
            self.stats.set_stream_status(False, self._fail_count)

    @property
    def frame_interval_seconds(self):
        # HLS delivers whole segments in bursts. Reading those at decode speed
        # overwrites almost every frame in the latest-frame slot, followed by
        # seconds of starvation. RTSP already paces delivery on the network.
        if ".m3u8" in self.url.lower() and self._effective_fps > 0:
            if isinstance(self.cap, BufferedHlsCapture):
                return 1.0 / self.cap.get(cv2.CAP_PROP_FPS)
            return 1.0 / self._effective_fps
        return 0.0

    def read(self):
        with self._state_lock:
            pending_url = self._pending_source_url
            self._pending_source_url = None
        if pending_url:
            self._source_urls = [pending_url]
            self._source_open_failures = [0]
            self._source_index = 0
            self.url = pending_url
            if isinstance(self.cap, BufferedHlsCapture):
                self.cap.url = pending_url
            else:
                self._reset_requested = True
        if self.cap is None:
            self._reset_requested = True
        if self._refresh_latest_requested:
            self._refresh_latest_requested = False
            self._reset_requested = False
            self._connect()
            return self._read_most_recent_frame()

        if self._reset_requested:
            self._reset_requested = False
            self._connect()

        with self._state_lock:
            self._read_started_monotonic = time.perf_counter()
        ret, frame = self.cap.read()
        with self._state_lock:
            self._read_started_monotonic = 0.0
        if not ret:
            if isinstance(self.cap, BufferedHlsCapture) and self.cap.unsupported:
                logger.warning("Formato HLS requer captura nativa; desativando buffer de segmentos.")
                self._buffered_hls = False
                self._connect()
                return False, None
            self._fail_count += 1
            if self.stats is not None:
                self.stats.set_stream_status(False, self._fail_count)

            if self._fail_count >= self.MAX_FAILURES:
                logger.warning("Stream perdido — reconectando...")
                self._connect()

            return False, None

        self._fail_count = 0
        with self._state_lock:
            self._last_frame_monotonic = time.perf_counter()
        if self.stats is not None:
            self.stats.set_stream_status(True, self._fail_count)
        return True, frame

    def _read_most_recent_frame(self):
        if self.cap is None:
            return False, None

        deadline = time.perf_counter() + self.LIVE_EDGE_DRAIN_SECONDS
        last_frame = None
        drained_frames = 0

        while drained_frames < self.LIVE_EDGE_MAX_FRAMES and time.perf_counter() < deadline:
            read_started = time.perf_counter()
            ret, frame = self.cap.read()
            read_elapsed_ms = (time.perf_counter() - read_started) * 1000.0

            if not ret:
                break

            last_frame = frame
            drained_frames += 1

            # Reads that stay "fast" usually indicate buffered backlog.
            # Once the read starts blocking, we are likely near the live edge.
            if read_elapsed_ms >= self.LIVE_EDGE_SLOW_READ_MS:
                break

        if last_frame is not None:
            logger.info(
                "Atualizacao para frame mais atual concluida | frames descartados: %s",
                max(0, drained_frames - 1),
            )
            self._fail_count = 0
            if self.stats is not None:
                self.stats.set_stream_status(True, self._fail_count)
            return True, last_frame

        if self.stats is not None:
            self.stats.set_stream_status(False, self._fail_count)
        return False, None

    def request_reset(self):
        logger.info("Reset manual do stream solicitado.")
        self._reset_requested = True

    def request_source_url(self, url):
        with self._state_lock:
            self._pending_source_url = url

    def request_refresh_latest(self):
        logger.info("Atualizacao manual para o frame mais atual solicitada.")
        self._refresh_latest_requested = True

    def get_stall_diagnostics(self) -> dict:
        with self._state_lock:
            read_started_monotonic = self._read_started_monotonic
            last_frame_monotonic = self._last_frame_monotonic
            forced_interrupt_count = self._forced_interrupt_count

        now_perf = time.perf_counter()
        read_duration_seconds = (
            max(0.0, now_perf - read_started_monotonic)
            if read_started_monotonic > 0.0
            else 0.0
        )
        last_frame_age_seconds = (
            max(0.0, now_perf - last_frame_monotonic)
            if last_frame_monotonic > 0.0
            else None
        )
        return {
            "url": self.url,
            "readDurationSeconds": read_duration_seconds,
            "lastFrameAgeSeconds": last_frame_age_seconds,
            "forcedInterruptCount": forced_interrupt_count,
            "failCount": self._fail_count,
        }

    def force_interrupt_stalled_read(self, reason: str) -> bool:
        if self.cap is None:
            return False

        with self._state_lock:
            self._forced_interrupt_count += 1
            forced_interrupt_count = self._forced_interrupt_count

        logger.warning(
            "Captura travada; forçando reset do stream (%s) | fonte=%s | tentativas=%s",
            reason,
            self.url,
            forced_interrupt_count,
        )
        self._reset_requested = True
        if self.stats is not None:
            self.stats.set_stream_status(False, max(self._fail_count, 1))
        return True

    def release(self):
        if self.cap:
            self.cap.release()

