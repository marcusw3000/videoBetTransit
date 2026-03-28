const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api'
const SIGNALR_BASE_URL = import.meta.env.VITE_SIGNALR_BASE_URL || 'http://localhost:5000'
const MJPEG_URL = import.meta.env.VITE_MJPEG_URL || 'http://127.0.0.1:8090/video_feed'
const CAMERA_PREVIEW_URL = import.meta.env.VITE_CAMERA_PREVIEW_URL || MJPEG_URL

export { API_BASE_URL, SIGNALR_BASE_URL, MJPEG_URL, CAMERA_PREVIEW_URL }
