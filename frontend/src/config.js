const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080'
const SIGNALR_BASE_URL = import.meta.env.VITE_SIGNALR_BASE_URL || 'http://localhost:8080'
const MJPEG_TOKEN = import.meta.env.VITE_MJPEG_TOKEN || 'CHANGE_ME'
const WEBRTC_URL = import.meta.env.VITE_WEBRTC_URL || null
const HLS_URL = import.meta.env.VITE_HLS_URL || null

// MJPEG served directly by vision-worker on port 8090
const RAW_MJPEG_URL = import.meta.env.VITE_MJPEG_URL || 'http://localhost:8090/video_feed'
const MJPEG_HEALTH_URL = import.meta.env.VITE_MJPEG_HEALTH_URL || 'http://localhost:8090/health'

const withToken = (url) => (
  MJPEG_TOKEN
    ? `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(MJPEG_TOKEN)}`
    : url
)
const MJPEG_URL = withToken(RAW_MJPEG_URL)

export { API_BASE_URL, SIGNALR_BASE_URL, WEBRTC_URL, HLS_URL, MJPEG_URL, MJPEG_HEALTH_URL }
