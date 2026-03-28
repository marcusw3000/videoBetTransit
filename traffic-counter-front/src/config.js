const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api'
const SIGNALR_BASE_URL = import.meta.env.VITE_SIGNALR_BASE_URL || 'http://localhost:5000'
const BACKEND_API_KEY = import.meta.env.VITE_BACKEND_API_KEY || 'SUA_API_KEY'
const MJPEG_TOKEN = import.meta.env.VITE_MJPEG_TOKEN || 'SUA_MJPEG_TOKEN'
const RAW_MJPEG_URL = import.meta.env.VITE_MJPEG_URL || 'http://127.0.0.1:8090/video_feed'
const withToken = (url) => (
  MJPEG_TOKEN
    ? `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(MJPEG_TOKEN)}`
    : url
)
const MJPEG_URL = withToken(RAW_MJPEG_URL)

export { API_BASE_URL, SIGNALR_BASE_URL, BACKEND_API_KEY, MJPEG_URL }
