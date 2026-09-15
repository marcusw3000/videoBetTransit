from __future__ import annotations
import subprocess
import threading
import time
import logging
from runtime_stats import RuntimeStats
logger = logging.getLogger(__name__)


class RtspFramePublisher:
    MAX_RESTART_BACKOFF_SECONDS = 5.0

    def __init__(
        self,
        *,
        rtsp_url: str,
        fps: float,
        ffmpeg_bin: str = "ffmpeg",
        stats: RuntimeStats | None = None,
    ):
        self.rtsp_url = rtsp_url
        self.fps = max(1.0, float(fps))
        self.ffmpeg_bin = ffmpeg_bin or "ffmpeg"
        self.stats = stats
        self._process: subprocess.Popen | None = None
        self._shape = None
        self._restart_count = 0
        self._lock = threading.Lock()
        self._next_restart_at = 0.0
        self._restart_backoff_seconds = 0.5

    @property
    def restart_count(self) -> int:
        with self._lock:
            return self._restart_count

    def _build_command(self, frame_shape) -> list[str]:
        height, width = frame_shape[:2]
        gop = max(1, int(round(self.fps)))
        return [
            self.ffmpeg_bin,
            "-loglevel", "warning",
            "-fflags", "nobuffer",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}",
            "-r", f"{self.fps:.02f}",
            "-i", "-",
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-bf", "0",
            "-g", str(gop),
            "-keyint_min", str(gop),
            "-rtsp_transport", "tcp",
            "-f", "rtsp",
            self.rtsp_url,
        ]

    def _set_stats(self, healthy: bool):
        if self.stats is not None:
            self.stats.set_publisher_status(
                healthy,
                restart_count=self.restart_count,
                active_transport="webrtc" if healthy else "mjpeg",
            )

    def _start_process(self, frame_shape):
        self.stop()
        command = self._build_command(frame_shape)
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        logger.info("Iniciando publisher RTSP: %s", self.rtsp_url)
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            self._shape = tuple(frame_shape[:2])
            self._next_restart_at = 0.0
            self._restart_backoff_seconds = 0.5
            self._set_stats(True)
            return True
        except Exception as exc:
            logger.warning("Falha ao iniciar publisher RTSP: %s", exc)
            self._process = None
            self._shape = None
            self._set_stats(False)
            return False

    def publish(self, frame):
        if frame is None:
            return False

        now_ts = time.time()
        frame_shape = tuple(frame.shape[:2])
        process = self._process
        process_exited = process is not None and process.poll() is not None
        if process_exited:
            logger.warning(
                "Publisher RTSP saiu inesperadamente (code=%s). Novo restart em %.1fs.",
                process.poll(),
                max(0.0, self._next_restart_at - now_ts) if self._next_restart_at > now_ts else 0.0,
            )
        if process is None or self._shape != frame_shape or process_exited:
            if self._next_restart_at > now_ts:
                self._set_stats(False)
                return False
            with self._lock:
                self._restart_count += 1
            if not self._start_process(frame.shape):
                self._next_restart_at = time.time() + self._restart_backoff_seconds
                self._restart_backoff_seconds = min(
                    self.MAX_RESTART_BACKOFF_SECONDS,
                    max(0.5, self._restart_backoff_seconds * 2.0),
                )
                return False
            process = self._process

        try:
            assert process is not None and process.stdin is not None
            process.stdin.write(frame.tobytes())
            process.stdin.flush()
            if self.stats is not None:
                self.stats.record_published_frame()
            self._set_stats(True)
            return True
        except Exception as exc:
            logger.warning("Falha ao publicar frame no RTSP: %s", exc)
            self._set_stats(False)
            self._next_restart_at = time.time() + self._restart_backoff_seconds
            self._restart_backoff_seconds = min(
                self.MAX_RESTART_BACKOFF_SECONDS,
                max(0.5, self._restart_backoff_seconds * 2.0),
            )
            self.stop()
            return False

    def stop(self):
        process = self._process
        self._process = None
        self._shape = None
        if process is None:
            self._set_stats(False)
            return

        try:
            if process.stdin is not None:
                process.stdin.close()
        except Exception:
            pass

        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        finally:
            self._set_stats(False)

