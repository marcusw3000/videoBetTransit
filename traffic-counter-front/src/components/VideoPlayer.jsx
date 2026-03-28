import { useState } from 'react'

export default function VideoPlayer({ src, title = 'Ao Vivo', onStreamStatusChange }) {
  const [hasError, setHasError] = useState(false)

  function handleLoad() {
    setHasError(false)
    onStreamStatusChange?.('online')
  }

  function handleError() {
    setHasError(true)
    onStreamStatusChange?.('error')
  }

  return (
    <div className="card video-card">
      <div className="video-header">
        <div>
          <span className="label">Transmissao</span>
          <h2>{title}</h2>
        </div>

        <div className="live-dot-wrapper">
          <span className="live-dot" />
          <span>AO VIVO</span>
        </div>
      </div>

      <div className="video-frame">
        {!src && <div className="video-overlay-message">Defina uma URL MJPEG para iniciar.</div>}
        {src && hasError && <div className="video-overlay-message">Falha ao carregar o stream anotado.</div>}
        {src && !hasError && (
          <img
            src={src}
            alt={title}
            className="video-element"
            onLoad={handleLoad}
            onError={handleError}
          />
        )}
      </div>
    </div>
  )
}
