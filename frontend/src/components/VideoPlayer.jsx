import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Hls from 'hls.js'

const WEBRTC_BOOT_TIMEOUT_MS = 3500
const CAMERA_TRANSITION_TIMEOUT_MS = 5000
const CAMERA_TRANSITION_MIN_VISIBLE_MS = 250
const WRAPPER_SOURCE = 'videobettransit-webrtc-wrapper'

function buildReloadedSrc(src, reloadToken) {
  if (!src) return ''
  const separator = src.includes('?') ? '&' : '?'
  return `${src}${separator}reload=${reloadToken}`
}

function getPreferredMode(webrtcSrc, primarySrc, fallbackSrc) {
  if (fallbackSrc) return 'mjpeg'
  if (primarySrc) return 'hls'
  if (webrtcSrc) return 'webrtc'
  return 'webrtc'
}

export default function VideoPlayer({
  webrtcSrc = '',
  src = '',
  fallbackSrc = '',
  title = 'Ao Vivo',
  countValue = 0,
  transitionLabel = '',
  transitioning = false,
  onStreamStatusChange,
}) {
  const videoRef = useRef(null)
  const hlsRef = useRef(null)
  const syncIntervalRef = useRef(null)
  const transitionTimeoutRef = useRef(null)
  const transitionStartedAtRef = useRef(0)
  const previousSourceSignatureRef = useRef('')
  const previousExternalTransitioningRef = useRef(false)
  const [mode, setMode] = useState(() => getPreferredMode(webrtcSrc, src, fallbackSrc))
  const [hasError, setHasError] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)
  const [webrtcReady, setWebrtcReady] = useState(false)
  const [isTransitioning, setIsTransitioning] = useState(false)

  const reloadedWebRtcSrc = useMemo(() => buildReloadedSrc(webrtcSrc, reloadToken), [reloadToken, webrtcSrc])
  const primarySrc = useMemo(() => buildReloadedSrc(src, reloadToken), [reloadToken, src])
  const mjpegFallbackSrc = useMemo(() => buildReloadedSrc(fallbackSrc, reloadToken), [fallbackSrc, reloadToken])
  const sourceSignature = useMemo(
    () => JSON.stringify({
      webrtcSrc: String(webrtcSrc || '').trim(),
      src: String(src || '').trim(),
      fallbackSrc: String(fallbackSrc || '').trim(),
      title: String(title || '').trim(),
    }),
    [fallbackSrc, src, title, webrtcSrc],
  )
  const effectiveTransitionLabel = useMemo(
    () => String(transitionLabel || title || 'Nova câmera').trim(),
    [title, transitionLabel],
  )

  const notifyStatus = useCallback((status) => {
    onStreamStatusChange?.(status)
  }, [onStreamStatusChange])

  const clearTransitionTimer = useCallback(() => {
    if (transitionTimeoutRef.current) {
      window.clearTimeout(transitionTimeoutRef.current)
      transitionTimeoutRef.current = null
    }
  }, [])

  const beginCameraTransition = useCallback(() => {
    clearTransitionTimer()
    transitionStartedAtRef.current = Date.now()
    setIsTransitioning(true)
    setHasError(false)
    transitionTimeoutRef.current = window.setTimeout(() => {
      setIsTransitioning(false)
    }, CAMERA_TRANSITION_TIMEOUT_MS)
  }, [clearTransitionTimer])

  const finishCameraTransition = useCallback(() => {
    clearTransitionTimer()
    const elapsed = Date.now() - transitionStartedAtRef.current
    const remaining = Math.max(0, CAMERA_TRANSITION_MIN_VISIBLE_MS - elapsed)

    if (remaining === 0) {
      setIsTransitioning(false)
      return
    }

    transitionTimeoutRef.current = window.setTimeout(() => {
      setIsTransitioning(false)
      transitionTimeoutRef.current = null
    }, remaining)
  }, [clearTransitionTimer])

  const clearHlsResources = useCallback(() => {
    if (syncIntervalRef.current) {
      clearInterval(syncIntervalRef.current)
      syncIntervalRef.current = null
    }

    if (hlsRef.current) {
      hlsRef.current.destroy()
      hlsRef.current = null
    }
  }, [])

  const switchToFallback = useCallback(() => {
    clearHlsResources()
    setWebrtcReady(false)

    if (!mjpegFallbackSrc) {
      finishCameraTransition()
      setHasError(true)
      notifyStatus('error')
      return
    }

    setMode('mjpeg')
    setHasError(false)
    notifyStatus('fallback')
  }, [clearHlsResources, finishCameraTransition, mjpegFallbackSrc, notifyStatus])

  const switchToHls = useCallback(() => {
    if (!primarySrc) {
      switchToFallback()
      return
    }

    clearHlsResources()
    setWebrtcReady(false)
    setMode('hls')
    setHasError(false)
    notifyStatus('connecting')
  }, [clearHlsResources, notifyStatus, primarySrc, switchToFallback])

  const handleReset = useCallback(() => {
    setHasError(false)
    setWebrtcReady(false)
    setMode(getPreferredMode(webrtcSrc, src, fallbackSrc))
    setReloadToken(Date.now())
    beginCameraTransition()
    notifyStatus('reconnecting')
  }, [beginCameraTransition, fallbackSrc, notifyStatus, src, webrtcSrc])

  useEffect(() => {
    setMode(getPreferredMode(webrtcSrc, src, fallbackSrc))
    setHasError(false)
    setWebrtcReady(false)
  }, [fallbackSrc, src, webrtcSrc])

  useEffect(() => {
    const previous = previousSourceSignatureRef.current
    const previousExternalTransitioning = previousExternalTransitioningRef.current
    previousSourceSignatureRef.current = sourceSignature
    previousExternalTransitioningRef.current = Boolean(transitioning)

    if (!previous) {
      return
    }

    if (
      previous !== sourceSignature
      && (webrtcSrc || src || fallbackSrc)
      && !transitioning
      && !previousExternalTransitioning
    ) {
      beginCameraTransition()
    }
  }, [beginCameraTransition, fallbackSrc, sourceSignature, src, transitioning, webrtcSrc])

  useEffect(() => {
    if (!reloadedWebRtcSrc || mode !== 'webrtc') return undefined

    setWebrtcReady(false)
    notifyStatus('connecting')

    const handleMessage = (event) => {
      const payload = event.data
      if (!payload || payload.source !== WRAPPER_SOURCE) return

      if (payload.type === 'first-frame' || payload.type === 'playing') {
        setWebrtcReady(true)
        setHasError(false)
        finishCameraTransition()
        notifyStatus('online')
        return
      }

      if (payload.type === 'stalled' || payload.type === 'error') {
        switchToHls()
      }
    }

    window.addEventListener('message', handleMessage)
    const timerId = window.setTimeout(() => {
      setWebrtcReady((ready) => {
        if (!ready) {
          switchToHls()
        }
        return ready
      })
    }, WEBRTC_BOOT_TIMEOUT_MS)

    return () => {
      window.clearTimeout(timerId)
      window.removeEventListener('message', handleMessage)
    }
  }, [finishCameraTransition, mode, notifyStatus, reloadedWebRtcSrc, switchToHls])

  useEffect(() => {
    const video = videoRef.current
    if (!video || !primarySrc || mode !== 'hls') return undefined

    clearHlsResources()
    video.pause()
    video.removeAttribute('src')
    video.load()

    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = primarySrc
      const handleLoaded = () => {
        setHasError(false)
        finishCameraTransition()
        notifyStatus('online')
      }
      const handleNativeError = () => switchToFallback()

      video.addEventListener('loadeddata', handleLoaded)
      video.addEventListener('error', handleNativeError)
      void video.play().catch(() => {})

      return () => {
        video.removeEventListener('loadeddata', handleLoaded)
        video.removeEventListener('error', handleNativeError)
      }
    }

    if (!Hls.isSupported()) {
      const fallbackTimerId = window.setTimeout(() => switchToFallback(), 0)
      return () => window.clearTimeout(fallbackTimerId)
    }

    const hls = new Hls({
      lowLatencyMode: true,
      liveSyncDurationCount: 1,
      liveMaxLatencyDurationCount: 3,
      maxLiveSyncPlaybackRate: 1.2,
      backBufferLength: 6,
      enableWorker: true,
    })

    hlsRef.current = hls
    hls.loadSource(primarySrc)
    hls.attachMedia(video)

    const handleLoaded = () => {
      setHasError(false)
      notifyStatus('online')
      void video.play().catch(() => {})
    }

    hls.on(Hls.Events.MANIFEST_PARSED, handleLoaded)
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

    syncIntervalRef.current = window.setInterval(() => {
      const media = videoRef.current
      const currentHls = hlsRef.current
      if (!media || !currentHls || !Number.isFinite(media.currentTime)) return

      const liveSyncPosition = currentHls.liveSyncPosition
      if (Number.isFinite(liveSyncPosition) && media.currentTime < liveSyncPosition - 1.25) {
        media.currentTime = liveSyncPosition
      }
    }, 2500)

    return () => {
      clearHlsResources()
    }
  }, [clearHlsResources, mode, notifyStatus, primarySrc, switchToFallback])

  useEffect(() => () => {
    clearHlsResources()
    clearTransitionTimer()
  }, [clearHlsResources, clearTransitionTimer])

  function handleFallbackLoad() {
    setHasError(false)
    finishCameraTransition()
    notifyStatus('online')
  }

  function handleFallbackError() {
    finishCameraTransition()
    setHasError(true)
    notifyStatus('error')
  }

  const liveBadgeLabel = mode === 'webrtc' ? 'WEBRTC' : mode === 'hls' ? 'HLS' : 'MJPEG'

  return (
    <div className="card video-card">
      <div className="video-header">
        <div>
          <span className="label">Transmissão</span>
          <h2>{title}</h2>
        </div>

        <div className="live-dot-wrapper">
          <span className="live-dot" />
          <span>{liveBadgeLabel}</span>
        </div>
      </div>

      <div className="video-toolbar">
        <button type="button" className="secondary-button" onClick={handleReset}>
          Resetar vídeo
        </button>
      </div>

      <div className={`video-frame${isTransitioning ? ' video-frame-transitioning' : ''}`}>
        <div className="video-count-overlay">
          <span className="video-count-label">Contagem da Rodada</span>
          <strong className="video-count-value">{countValue ?? 0}</strong>
        </div>

        {(transitioning || isTransitioning) && (
          <div className="video-transition-overlay" aria-live="polite">
            <div className="video-transition-chip">
              <span className="video-transition-spinner" aria-hidden="true" />
              <span>Trocando câmera...</span>
            </div>
            <strong className="video-transition-title">{effectiveTransitionLabel}</strong>
            <span className="video-transition-subtitle">Preparando a próxima transmissão ao vivo</span>
          </div>
        )}

        {!webrtcSrc && !src && !fallbackSrc && (
          <div className="video-overlay-message">Defina uma URL de stream para iniciar.</div>
        )}

        {(webrtcSrc || src || fallbackSrc) && hasError && !(transitioning || isTransitioning) && (
          <div className="video-overlay-message">
            <div className="video-overlay-stack">
              <span>Falha ao carregar a transmissão.</span>
              <button type="button" className="secondary-button" onClick={handleReset}>
                Tentar novamente
              </button>
            </div>
          </div>
        )}

        {!hasError && !(transitioning || isTransitioning) && mode === 'webrtc' && reloadedWebRtcSrc && (
          <iframe
            key={reloadedWebRtcSrc}
            src={reloadedWebRtcSrc}
            title={title}
            className="video-element"
            allow="autoplay"
          />
        )}

        {!hasError && !(transitioning || isTransitioning) && mode === 'hls' && primarySrc && (
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

        {!hasError && !(transitioning || isTransitioning) && mode === 'mjpeg' && mjpegFallbackSrc && (
          <img
            key={mjpegFallbackSrc}
            src={mjpegFallbackSrc}
            alt={title}
            className="video-element"
            onLoad={handleFallbackLoad}
            onError={handleFallbackError}
          />
        )}
      </div>
    </div>
  )
}
