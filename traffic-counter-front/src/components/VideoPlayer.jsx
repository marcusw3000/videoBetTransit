import { useState } from 'react'

export default function VideoPlayer({ src, title = 'Ao Vivo' }) {
  const [hasError, setHasError] = useState(false)

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
        {!src && <div className="video-overlay-message">Defina uma URL MJPEG para iniciar.</div>}
        {src && hasError && <div className="video-overlay-message">Falha ao carregar o stream anotado.</div>}
        {src && !hasError && (
          <img
            src={src}
            alt={title}
            className="video-element"
            onError={() => setHasError(true)}
          />
        )}
      </div>
    </div>
  )
}
