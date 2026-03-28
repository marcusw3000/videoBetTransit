import { useEffect, useMemo, useState } from 'react'

export default function VideoPlayer({ src, title = 'Ao Vivo', onStreamStatusChange, resetKey }) {
  const [hasError, setHasError] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)

  const streamSrc = useMemo(() => {
    if (!src) return ''
    const separator = src.includes('?') ? '&' : '?'
    return `${src}${separator}reload=${reloadToken}`
  }, [src, reloadToken])

  function handleLoad() {
    setHasError(false)
    onStreamStatusChange?.('online')
  }

  function handleError() {
    setHasError(true)
    onStreamStatusChange?.('error')
  }

  function handleReset() {
    setHasError(false)
    setReloadToken(Date.now())
    onStreamStatusChange?.('reconnecting')
  }

  useEffect(() => {
    if (!resetKey) return
    handleReset()
  }, [resetKey])

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

      <div className="video-toolbar">
        <button type="button" className="secondary-button" onClick={handleReset}>
          Resetar Video
        </button>
      </div>

      <div className="video-frame">
        {!src && <div className="video-overlay-message">Defina uma URL MJPEG para iniciar.</div>}
        {src && hasError && (
          <div className="video-overlay-message">
            <div className="video-overlay-stack">
              <span>Falha ao carregar o stream anotado.</span>
              <button type="button" className="secondary-button" onClick={handleReset}>
                Tentar Novamente
              </button>
            </div>
          </div>
        )}
        {src && !hasError && (
          <img
            key={streamSrc}
            src={streamSrc}
            alt={title}
            className="video-element"
            onLoad={handleLoad}
            onError={handleError}
            draggable={false}
          />
        )}
      </div>
    </div>
  )
}
