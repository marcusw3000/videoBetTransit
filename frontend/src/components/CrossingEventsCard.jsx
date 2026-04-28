function shortHash(value) {
  const hash = String(value || '').trim()
  if (!hash) return '--'
  return `${hash.slice(0, 10)}...`
}

function formatDateTime(value, locale = 'pt-BR', timezone = 'America/Sao_Paulo') {
  if (!value) return '--'

  try {
    return new Date(value).toLocaleString(locale, {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      timeZone: timezone,
    })
  } catch {
    return value
  }
}

export default function CrossingEventsCard({
  events = [],
  title = 'Cruzamentos Oficiais',
  locale = 'pt-BR',
  timezone = 'America/Sao_Paulo',
  limit = 8,
  compact = false,
  emptyMessage = 'Nenhum crossing oficial registrado ainda.',
}) {
  const visibleEvents = (Array.isArray(events) ? events : []).slice(0, limit)

  return (
    <div className="card crossing-events-card">
      <div className="round-timeline-head">
        <div>
          <span className="label">{title}</span>
          <h3>{compact ? 'Ultimos eventos' : 'Ultimos cruzamentos persistidos'}</h3>
        </div>
      </div>

      {visibleEvents.length === 0 ? (
        <div className="empty-state">{emptyMessage}</div>
      ) : (
        <div className="crossing-events-list">
          {visibleEvents.map((event) => (
            <div key={event.id || event.eventHash} className="crossing-event-row">
              <div className="crossing-event-main">
                <strong>{event.objectClass || event.vehicleType} #{event.trackId}</strong>
                <span>{formatDateTime(event.timestampUtc, locale, timezone)}</span>
              </div>
              <div className="crossing-event-meta">
                <span>Count: {event.countBefore ?? '--'} {'->'} {event.countAfter ?? '--'}</span>
                {event.countMethod && (
                  <span>
                    Metodo: {event.countMethod === 'fallback' ? 'fallback' : 'primary'}
                    {event.countMethod === 'fallback' && event.fallbackBandPx != null ? ` (${event.fallbackBandPx}px)` : ''}
                  </span>
                )}
                <span>Direcao: {event.direction || '--'}</span>
                <span>Linha: {event.lineId || '--'}</span>
                {event.streamProfileId && <span>Perfil: {event.streamProfileId}</span>}
                <span>Hash: {shortHash(event.eventHash)}</span>
              </div>
              {event.snapshotUrl && (
                <div className="crossing-event-evidence">
                  <a href={event.snapshotUrl} target="_blank" rel="noreferrer">
                    Abrir snapshot
                  </a>
                  <span className="crossing-event-snapshot">{event.snapshotUrl}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
