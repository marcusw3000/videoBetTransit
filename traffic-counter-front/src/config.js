const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api'
const SIGNALR_BASE_URL = import.meta.env.VITE_SIGNALR_BASE_URL || 'http://localhost:5000'
const MJPEG_TOKEN = import.meta.env.VITE_MJPEG_TOKEN || 'SUA_MJPEG_TOKEN'
const WEBRTC_BASE_URL = (import.meta.env.VITE_WEBRTC_BASE_URL || 'http://127.0.0.1:8889').replace(/\/+$/, '')
const HLS_BASE_URL = (import.meta.env.VITE_HLS_BASE_URL || 'http://127.0.0.1:8888').replace(/\/+$/, '')
const WEBRTC_URL = import.meta.env.VITE_WEBRTC_URL
  || `${WEBRTC_BASE_URL}/processed/${import.meta.env.VITE_CAMERA_ID || 'cam_001'}/?controls=false&muted=true&autoplay=true&playsInline=true`
const HLS_URL = import.meta.env.VITE_HLS_URL || `${HLS_BASE_URL}/processed/${import.meta.env.VITE_CAMERA_ID || 'cam_001'}/index.m3u8`
const RAW_MJPEG_URL = import.meta.env.VITE_MJPEG_URL || `${SIGNALR_BASE_URL}/proxy/video-feed`
const MJPEG_HEALTH_URL = import.meta.env.VITE_MJPEG_HEALTH_URL || `${SIGNALR_BASE_URL}/proxy/health`

function normalizeCameraId(value) {
  const normalized = String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '_')
    .replace(/^_+|_+$/g, '')

  return normalized || 'cam_001'
}

function normalizeStreamPath(path, fallbackCameraId = '') {
  const normalized = String(path || '').trim().replace(/^\/+|\/+$/g, '')
  return normalized || `processed/${normalizeCameraId(fallbackCameraId)}`
}

function buildWebRtcUrlFromPath(path, cameraId = '') {
  const normalizedPath = normalizeStreamPath(path, cameraId)
  return `${WEBRTC_BASE_URL}/${normalizedPath}/?controls=false&muted=true&autoplay=true&playsInline=true`
}

function buildHlsUrlFromPath(path, cameraId = '') {
  const normalizedPath = normalizeStreamPath(path, cameraId)
  return `${HLS_BASE_URL}/${normalizedPath}/index.m3u8`
}

const withToken = (url) => (
  MJPEG_TOKEN
    ? `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(MJPEG_TOKEN)}`
    : url
)
const MJPEG_URL = RAW_MJPEG_URL.includes('/proxy/')
  ? RAW_MJPEG_URL
  : withToken(RAW_MJPEG_URL)

export {
  API_BASE_URL,
  SIGNALR_BASE_URL,
  WEBRTC_URL,
  HLS_URL,
  MJPEG_URL,
  MJPEG_HEALTH_URL,
  normalizeCameraId,
  normalizeStreamPath,
  buildWebRtcUrlFromPath,
  buildHlsUrlFromPath,
}
