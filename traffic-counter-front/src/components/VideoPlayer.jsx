import { useEffect, useRef, useState } from 'react'
import Hls from 'hls.js'
import VideoOverlayCanvas from './VideoOverlayCanvas'

export default function VideoPlayer({ src, title = 'Ao Vivo', detectionFrame = null }) {
  const videoRef = useRef(null)
  const [isReady, setIsReady] = useState(false)
  const [hasError, setHasError] = useState(false)

  useEffect(() => {
    const video = videoRef.current
    if (!video || !src) return

    let hls = null

    setIsReady(false)
    setHasError(false)

    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = src
      video.addEventListener(
        'loadedmetadata',
        () => {
          setIsReady(true)
          video.play().catch(() => {})
        },
        { once: true }
      )
    } else if (Hls.isSupported()) {
      hls = new Hls({
        enableWorker: true,
        lowLatencyMode: true
      })

      hls.loadSource(src)
      hls.attachMedia(video)

      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        setIsReady(true)
        video.play().catch(() => {})
      })

      hls.on(Hls.Events.ERROR, (_, data) => {
        console.error('HLS error:', data)
        if (data?.fatal) {
          setHasError(true)
        }
      })
    } else {
      setHasError(true)
    }

    return () => {
      if (hls) {
        hls.destroy()
      }
    }
  }, [src])

  return (
    <div className="card video-card">
      <div className="video-header">
        <div>
          <span className="label">Transmissão</span>
          <h2>{title}</h2>
        </div>

        <div className="live-dot-wrapper">
          <span className="live-dot" />
          <span>AO VIVO</span>
        </div>
      </div>

      <div className="video-frame">
        {!src && <div className="video-overlay-message">Defina uma URL .m3u8 para iniciar.</div>}
        {src && hasError && <div className="video-overlay-message">Falha ao carregar o vídeo.</div>}
        {src && !hasError && !isReady && <div className="video-overlay-message">Carregando stream...</div>}

        <video
          ref={videoRef}
          className="video-element"
          controls
          muted
          autoPlay
          playsInline
        />

        {/* Overlay canvas posicionado sobre o vídeo */}
        <VideoOverlayCanvas detectionFrame={detectionFrame} videoRef={videoRef} />
      </div>
    </div>
  )
}
