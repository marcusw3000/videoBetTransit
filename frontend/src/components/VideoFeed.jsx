import { useState } from 'react'

export default function VideoFeed({ src, title }) {
  const [error, setError] = useState(false)

  return (
    <div className="video-card">
      {src && !error ? (
        <img
          className="video-feed-img"
          src={src}
          alt={title || 'Video feed'}
          onError={() => setError(true)}
        />
      ) : (
        <div className="video-placeholder">
          <span className="video-placeholder-icon">📷</span>
          <span>Aguardando stream...</span>
          {error && (
            <button
              style={{ marginTop: '0.5rem', fontSize: '0.7rem', color: 'var(--gold)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
              onClick={() => setError(false)}
            >
              Tentar novamente
            </button>
          )}
        </div>
      )}
    </div>
  )
}
