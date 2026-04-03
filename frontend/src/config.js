const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api'
const SIGNALR_BASE_URL = import.meta.env.VITE_SIGNALR_BASE_URL || 'http://localhost:5000'
const MJPEG_TOKEN = import.meta.env.VITE_MJPEG_TOKEN || 'SUA_MJPEG_TOKEN'
const WEBRTC_URL = import.meta.env.VITE_WEBRTC_URL
  || 'http://127.0.0.1:8889/rodovia-live?controls=false&muted=true&autoplay=true&playsInline=true'
const HLS_URL = import.meta.env.VITE_HLS_URL || `${SIGNALR_BASE_URL}/proxy/hls/manifest`
const RAW_MJPEG_URL = import.meta.env.VITE_MJPEG_URL || `${SIGNALR_BASE_URL}/proxy/video-feed`
const MJPEG_HEALTH_URL = import.meta.env.VITE_MJPEG_HEALTH_URL || `${SIGNALR_BASE_URL}/proxy/health`
const withToken = (url) => (
  MJPEG_TOKEN
    ? `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(MJPEG_TOKEN)}`
    : url
)
const MJPEG_URL = RAW_MJPEG_URL.includes('/proxy/')
  ? RAW_MJPEG_URL
  : withToken(RAW_MJPEG_URL)

export { API_BASE_URL, SIGNALR_BASE_URL, WEBRTC_URL, HLS_URL, MJPEG_URL, MJPEG_HEALTH_URL }
