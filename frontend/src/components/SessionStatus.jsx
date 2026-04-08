import LiveBadge from './LiveBadge'

function fmt(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return iso
  }
}

export default function SessionStatus({ session, onStop, stopping }) {
  if (!session) return null

  return (
    <div className="card session-status">
      <div style={{ marginBottom: '0.75rem' }}>
        <LiveBadge status={session.status} />
      </div>

      {session.cameraName && (
        <div className="status-row">
          <span className="status-key">Câmera</span>
          <span className="status-val">{session.cameraName}</span>
        </div>
      )}

      {session.sourceUrl && (
        <div className="status-row">
          <span className="status-key">Fonte</span>
          <span className="status-val" style={{ fontSize: '0.7rem', opacity: 0.7 }}>{session.sourceUrl}</span>
        </div>
      )}

      {session.startedAt && (
        <div className="status-row">
          <span className="status-key">Início</span>
          <span className="status-val">{fmt(session.startedAt)}</span>
        </div>
      )}

      {session.failureReason && (
        <div className="status-row">
          <span className="status-key">Erro</span>
          <span className="status-val" style={{ color: 'var(--red-alert)', fontSize: '0.72rem' }}>
            {session.failureReason}
          </span>
        </div>
      )}

      {['Running', 'Degraded', 'Starting'].includes(session.status) && (
        <button
          className="stop-btn"
          onClick={onStop}
          disabled={stopping}
        >
          {stopping ? 'Parando...' : '■ Parar Sessão'}
        </button>
      )}
    </div>
  )
}
