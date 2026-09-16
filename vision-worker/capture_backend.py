"""Serialize FFmpeg's process-wide open options, restoring the caller's env."""
import os
import threading
import cv2

_open_lock = threading.Lock()


def open_ffmpeg_capture(url, params=None, options=''):
    with _open_lock:
        previous = os.environ.get('OPENCV_FFMPEG_CAPTURE_OPTIONS')
        try:
            if options:
                os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = options
            else:
                os.environ.pop('OPENCV_FFMPEG_CAPTURE_OPTIONS', None)
            return cv2.VideoCapture(url, cv2.CAP_FFMPEG, params or [])
        finally:
            if previous is None:
                os.environ.pop('OPENCV_FFMPEG_CAPTURE_OPTIONS', None)
            else:
                os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = previous
