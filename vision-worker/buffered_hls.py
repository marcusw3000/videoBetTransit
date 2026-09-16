"""Bounded MPEG-TS HLS prefetch for YouTube live sources.

Download compressed segments ahead of playback. OpenCV only reads complete
local segments, so HTTP playlist/segment stalls cannot block its decoder.
Other transports and encrypted/fMP4 playlists keep using native capture.
"""
from __future__ import annotations

import logging
import os
import queue
import tempfile
import threading
import time
from urllib.parse import urljoin

import cv2
import requests
from capture_backend import open_ffmpeg_capture

logger = logging.getLogger(__name__)


def parse_media_playlist(text: str, base_url: str):
    sequence = 0
    duration = 5.0
    segments = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith('#EXT-X-KEY:') and 'METHOD=NONE' not in line:
            raise ValueError('Encrypted HLS requires native capture')
        if line.startswith(('#EXT-X-MAP:', '#EXT-X-BYTERANGE:', '#EXT-X-STREAM-INF:')):
            raise ValueError('This playlist requires native capture')
        if line.startswith('#EXT-X-MEDIA-SEQUENCE:'):
            sequence = int(line.split(':', 1)[1])
        elif line.startswith('#EXT-X-TARGETDURATION:'):
            duration = max(1.0, float(line.split(':', 1)[1]))
        elif line and not line.startswith('#'):
            url = urljoin(base_url, line)
            if not url.startswith(('http://', 'https://')):
                raise ValueError('Unsupported segment transport')
            segments.append((sequence + len(segments), url))
    return duration, segments, '#EXT-X-ENDLIST' in text


class BufferedHlsCapture:
    MAX_SEGMENT_BYTES = 32 * 1024 * 1024
    MAX_PLAYLIST_BYTES = 16 * 1024 * 1024

    def __init__(self, url: str, *, timeout: float = 8.0, refresh_url=None):
        self.url = url
        self.timeout = timeout
        self.refresh_url = refresh_url
        self._queue = queue.Queue(maxsize=3)
        self._stop = threading.Event()
        self._unsupported = False
        self._decoder = None
        self._segment_path = None
        self._fps = 30.0
        self._thread = threading.Thread(target=self._download, daemon=True, name='hls-prefetch')
        self._thread.start()

    def _get(self, session, url, limit):
        start = time.monotonic()
        data = bytearray()
        with session.get(url, timeout=(3, self.timeout), stream=True) as response:
            response.raise_for_status()
            for chunk in response.iter_content(65536):
                if self._stop.is_set():
                    return b''
                if time.monotonic() - start > self.timeout or len(data) + len(chunk) > limit:
                    raise requests.Timeout('HLS transfer exceeded bounded budget')
                data.extend(chunk)
        return bytes(data)

    def _download(self):
        next_sequence = None
        operation = 'playlist'
        last_refresh = 0.0
        with requests.Session() as session:
            session.headers['User-Agent'] = 'Mozilla/5.0'
            while not self._stop.is_set():
                try:
                    operation = 'playlist'
                    text = self._get(session, self.url, self.MAX_PLAYLIST_BYTES).decode('utf-8-sig')
                    duration, segments, finished = parse_media_playlist(text, self.url)
                    if not segments:
                        self._stop.wait(1)
                        continue
                    if next_sequence is None:
                        # Three segments of headroom, not the entire DVR archive.
                        next_sequence = segments[max(0, len(segments) - 3)][0]
                    if next_sequence < segments[0][0]:
                        logger.warning('HLS buffer overtaken by live window; resuming available segment')
                        next_sequence = segments[0][0]
                    for sequence, url in segments:
                        if sequence < next_sequence:
                            continue
                        if self._stop.is_set():
                            return
                        operation = 'segment'
                        data = self._get(session, url, self.MAX_SEGMENT_BYTES)
                        if not data:
                            break
                        while not self._stop.is_set():
                            try:
                                self._queue.put(data, timeout=.2)
                                break
                            except queue.Full:
                                continue
                        next_sequence = sequence + 1
                    if finished:
                        return
                    self._stop.wait(min(2.0, duration / 2))
                except ValueError:
                    self._unsupported = True
                    return
                except (requests.RequestException, UnicodeError) as exc:
                    # Never log signed URLs, cookies or provider response bodies.
                    response = getattr(exc, 'response', None)
                    status = response.status_code if response is not None else type(exc).__name__
                    logger.warning('HLS %s unavailable (%s); retrying', operation, status)
                    if self.refresh_url is not None and time.monotonic() - last_refresh >= 10:
                        last_refresh = time.monotonic()
                        try:
                            self.url = self.refresh_url()
                            logger.info('HLS URL renewed without resetting segment position')
                        except Exception:
                            logger.warning('HLS URL renewal unavailable')
                    self._stop.wait(1)

    def isOpened(self):
        return not self._stop.is_set() and not self._unsupported

    @property
    def unsupported(self):
        return self._unsupported

    def get(self, prop):
        if prop == cv2.CAP_PROP_FPS:
            return self._fps
        return self._decoder.get(prop) if self._decoder is not None else 0.0

    def set(self, *_args):
        return False

    def _close_segment(self):
        if self._decoder is not None:
            self._decoder.release()
            self._decoder = None
        if self._segment_path is not None:
            os.unlink(self._segment_path)
            self._segment_path = None

    def read(self):
        while not self._stop.is_set():
            if self._decoder is not None:
                ok, frame = self._decoder.read()
                if ok:
                    return True, frame
                self._close_segment()
            try:
                data = self._queue.get(timeout=1)
            except queue.Empty:
                return False, None
            with tempfile.NamedTemporaryFile(prefix='videobet-hls-', suffix='.ts', delete=False) as segment:
                self._segment_path = segment.name
                segment.write(data)
            self._decoder = open_ffmpeg_capture(self._segment_path)
            fps = self._decoder.get(cv2.CAP_PROP_FPS)
            if 1 <= fps <= 120:
                self._fps = fps
        return False, None

    def release(self):
        self._stop.set()
        self._close_segment()
