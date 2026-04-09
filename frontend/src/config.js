const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8080'
const SIGNALR_BASE_URL = import.meta.env.VITE_SIGNALR_BASE_URL || 'http://127.0.0.1:8080'
const MJPEG_TOKEN = import.meta.env.VITE_MJPEG_TOKEN || 'CHANGE_ME'

const WEBRTC_BASE_URL = (import.meta.env.VITE_WEBRTC_BASE_URL || 'http://127.0.0.1:8889').replace(/\/+$/, '')
const HLS_BASE_URL = (import.meta.env.VITE_HLS_BASE_URL || 'http://127.0.0.1:8888').replace(/\/+$/, '')
const MJPEG_BASE_URL = (import.meta.env.VITE_MJPEG_BASE_URL || 'http://127.0.0.1:8090/video_feed').replace(/\/+$/, '')
const MJPEG_HEALTH_URL = import.meta.env.VITE_MJPEG_HEALTH_URL || 'http://127.0.0.1:8090/health'

function normalizeCameraId(value) {
  const normalized = String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '_')
    .replace(/^_+|_+$/g, '')

  return normalized || 'cam_001'
}

function withToken(url) {
  return MJPEG_TOKEN
    ? `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(MJPEG_TOKEN)}`
    : url
}

function buildProcessedPath(cameraId) {
  return `processed/${normalizeCameraId(cameraId)}`
}

function buildWebRtcPlayerUrl(cameraId) {
  const path = buildProcessedPath(cameraId)
  return `${WEBRTC_BASE_URL}/${path}/`
}

function buildWebRtcWrapperUrl(cameraId) {
  const playerUrl = buildWebRtcPlayerUrl(cameraId)
  const wrapperBase = '/webrtc-wrapper.html'
  return `${wrapperBase}?src=${encodeURIComponent(playerUrl)}&cameraId=${encodeURIComponent(normalizeCameraId(cameraId))}`
}

function buildHlsUrl(cameraId) {
  const path = buildProcessedPath(cameraId)
  return `${HLS_BASE_URL}/${path}/index.m3u8`
}

function buildMjpegUrl() {
  return withToken(MJPEG_BASE_URL)
}

const MJPEG_URL = buildMjpegUrl()

export {
  API_BASE_URL,
  SIGNALR_BASE_URL,
  WEBRTC_BASE_URL,
  HLS_BASE_URL,
  MJPEG_BASE_URL,
  MJPEG_HEALTH_URL,
  MJPEG_TOKEN,
  MJPEG_URL,
  normalizeCameraId,
  buildProcessedPath,
  buildWebRtcPlayerUrl,
  buildWebRtcWrapperUrl,
  buildHlsUrl,
  buildMjpegUrl,
}
