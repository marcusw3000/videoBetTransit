import { useEffect, useMemo, useRef, useState } from 'react'
import Hls from 'hls.js'

function buildReloadedSrc(src, reloadToken) {
  if (!src) return ''
  const separator = src.includes('?') ? '&' : '?'
  return `${src}${separator}reload=${reloadToken}`
}

function getPreferredMode(webrtcSrc, primarySrc, fallbackSrc) {
  if (fallbackSrc) return 'mjpeg'
  if (webrtcSrc) return 'webrtc'
  if (primarySrc) return 'hls'
  return 'webrtc'
}

export default function VideoPlayer({
  webrtcSrc = '',
  src,
  fallbackSrc = '',
  title = 'Ao Vivo',
  countValue = 0,
  onStreamStatusChange,
  resetKey,
}) {
  const videoRef = useRef(null)
  const hlsRef = useRef(null)
  const syncIntervalRef = useRef(null)
  const [hasError, setHasError] = useState(false)
  const [mode, setMode] = useState(() => getPreferredMode(webrtcSrc, src, fallbackSrc))
  const [reloadToken, setReloadToken] = useState(0)
  const [iframeLoaded, setIframeLoaded] = useState(false)

  const reloadedWebRtcSrc = useMemo(() => buildReloadedSrc(webrtcSrc, reloadToken), [webrtcSrc, reloadToken])
  const primarySrc = useMemo(() => buildReloadedSrc(src, reloadToken), [src, reloadToken])
  const mjpegFallbackSrc = useMemo(
    () => buildReloadedSrc(fallbackSrc, reloadToken),
    [fallbackSrc, reloadToken],
  )

  function notifyStatus(status) {
    onStreamStatusChange?.(status)
  }

  function clearHlsResources() {
    if (syncIntervalRef.current) {
      clearInterval(syncIntervalRef.current)
      syncIntervalRef.current = null
    }

    if (hlsRef.current) {
      hlsRef.current.destroy()
      hlsRef.current = null
    }
  }

  function handleReset() {
    setHasError(false)
    setIframeLoaded(false)
    setMode(getPreferredMode(reloadedWebRtcSrc, primarySrc, mjpegFallbackSrc))
    setReloadToken(Date.now())
    notifyStatus('reconnecting')
  }

  function switchToHls() {
    if (!primarySrc) {
      switchToFallback()
      return
    }

    clearHlsResources()
    setMode('hls')
    setHasError(false)
    notifyStatus('fallback')
  }

  function switchToFallback() {
    clearHlsResources()

    if (!mjpegFallbackSrc) {
      setHasError(true)
      notifyStatus('error')
      return
    }

    setMode('mjpeg')
    setHasError(false)
    notifyStatus('fallback')
  }

  useEffect(() => {
    if (!resetKey) return
    handleReset()
  }, [resetKey])

  useEffect(() => {
    if (!reloadedWebRtcSrc || mode !== 'webrtc') return undefined

    setIframeLoaded(false)
    setHasError(false)

    const timerId = setTimeout(() => {
      if (!iframeLoaded) {
        switchToHls()
      }
    }, 4000)

    return () => clearTimeout(timerId)
  }, [reloadedWebRtcSrc, iframeLoaded, mode, reloadToken])

  useEffect(() => {
    const video = videoRef.current
    if (!video || !primarySrc || mode !== 'hls') return undefined

    clearHlsResources()
    video.pause()
    video.removeAttribute('src')
    video.load()

    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = primarySrc
      void video.play().catch(() => {})
      notifyStatus('online')
      return undefined
    }

    if (!Hls.isSupported()) {
      switchToFallback()
      return undefined
    }

    const hls = new Hls({
      lowLatencyMode: true,
      liveSyncDurationCount: 1,
      liveMaxLatencyDurationCount: 3,
      maxLiveSyncPlaybackRate: 1.2,
      backBufferLength: 8,
      enableWorker: true,
    })

    hlsRef.current = hls
    hls.loadSource(primarySrc)
    hls.attachMedia(video)

    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      setHasError(false)
      notifyStatus('online')
      void video.play().catch(() => {})
    })

    hls.on(Hls.Events.ERROR, (_, data) => {
      if (!data.fatal) return

      if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
        hls.startLoad()
        return
      }

      if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
        hls.recoverMediaError()
        return
      }

      switchToFallback()
    })

    syncIntervalRef.current = setInterval(() => {
      const media = videoRef.current
      const currentHls = hlsRef.current
      if (!media || !currentHls || !Number.isFinite(media.currentTime)) return

      const liveSyncPosition = currentHls.liveSyncPosition
      if (Number.isFinite(liveSyncPosition) && media.currentTime < liveSyncPosition - 1.5) {
        media.currentTime = liveSyncPosition
      }
    }, 3000)

    return () => {
      clearHlsResources()
    }
  }, [primarySrc, mode])

  useEffect(() => () => clearHlsResources(), [])

  function handleIframeLoad() {
    setIframeLoaded(true)
    setHasError(false)
    notifyStatus('online')
  }

  function handleFallbackLoad() {
    setHasError(false)
    notifyStatus('online')
  }

  function handleFallbackError() {
    setHasError(true)
    notifyStatus('error')
  }

  const liveBadgeLabel = mode === 'webrtc' ? 'WEBRTC' : mode === 'hls' ? 'HLS' : 'MJPEG'

  return (
    <div className="card video-card">
      <div className="video-header">
        <div>
          <span className="label">Transmissao</span>
          <h2>{title}</h2>
        </div>

        <div className="live-dot-wrapper">
          <span className="live-dot" />
          <span>{liveBadgeLabel}</span>
        </div>
      </div>

      <div className="video-toolbar">
        <button type="button" className="secondary-button" onClick={handleReset}>
          Resetar Video
        </button>
      </div>

      <div className="video-frame">
        <div className="video-count-overlay">
          <span className="video-count-label">Contagem Atual</span>
          <strong className="video-count-value">{countValue ?? 0}</strong>
        </div>

        {!webrtcSrc && !src && !fallbackSrc && (
          <div className="video-overlay-message">Defina uma URL de stream para iniciar.</div>
        )}

        {(webrtcSrc || src || fallbackSrc) && hasError && (
          <div className="video-overlay-message">
            <div className="video-overlay-stack">
              <span>Falha ao carregar a transmissao.</span>
              <button type="button" className="secondary-button" onClick={handleReset}>
                Tentar Novamente
              </button>
            </div>
          </div>
        )}

        {!hasError && mode === 'webrtc' && reloadedWebRtcSrc && (
          <iframe
            id={`webrtc-frame-${reloadToken}`}
            key={reloadedWebRtcSrc}
            src={reloadedWebRtcSrc}
            title={title}
            className="video-element"
            onLoad={handleIframeLoad}
            allow="autoplay; fullscreen"
          />
        )}

        {!hasError && mode === 'hls' && primarySrc && (
          <video
            key={primarySrc}
            ref={videoRef}
            className="video-element"
            muted
            playsInline
            autoPlay
            controls={false}
          />
        )}

        {!hasError && mode === 'mjpeg' && mjpegFallbackSrc && (
          <img
            key={mjpegFallbackSrc}
            src={mjpegFallbackSrc}
            alt={title}
            className="video-element"
            onLoad={handleFallbackLoad}
            onError={handleFallbackError}
            draggable={false}
          />
        )}
      </div>
    </div>
  )
}
