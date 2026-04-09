function formatTime(value, locale = 'pt-BR', timezone = 'America/Sao_Paulo') {
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

function getTimelineLabel(item) {
  if (item.kind === 'crossing_event') {
    return `${item.objectClass || 'veiculo'} #${item.trackId ?? '--'}`
  }

  switch (item.eventType) {
    case 'opened':
      return 'Round aberto'
    case 'bet_closed':
      return 'Apostas fechadas'
    case 'settling_started':
      return 'Apuracao iniciada'
    case 'settled':
      return 'Round liquidado'
    case 'voided':
      return 'Round anulado'
    case 'count_recorded':
      return `Count oficial: ${item.countValue ?? '--'}`
    default:
      return item.eventType || item.kind || 'evento'
  }
}

export default function RoundTimeline({
  items = [],
  title = 'Timeline Oficial',
  locale = 'pt-BR',
  timezone = 'America/Sao_Paulo',
  limit = null,
  compact = false,
  filter = 'all',
  onFilterChange = null,
}) {
  const normalizedItems = Array.isArray(items) ? items : []
  const filteredItems = normalizedItems.filter((item) => {
    if (filter === 'lifecycle') return item.kind === 'round_event'
    if (filter === 'crossings') return item.kind === 'crossing_event'
    return true
  })
  const visibleItems = (limit ? filteredItems.slice(-limit) : filteredItems).slice().reverse()

  return (
    <div className="card round-timeline-card">
      <div className="round-timeline-head">
        <div>
          <span className="label">{title}</span>
          <h3>{compact ? 'Round atual' : 'Cronologia do round'}</h3>
        </div>
        {typeof onFilterChange === 'function' && (
          <div className="timeline-filter">
            <button type="button" className={filter === 'all' ? 'is-active' : ''} onClick={() => onFilterChange('all')}>
              Todos
            </button>
            <button type="button" className={filter === 'lifecycle' ? 'is-active' : ''} onClick={() => onFilterChange('lifecycle')}>
              Lifecycle
            </button>
            <button type="button" className={filter === 'crossings' ? 'is-active' : ''} onClick={() => onFilterChange('crossings')}>
              Crossings
            </button>
          </div>
        )}
      </div>

      {visibleItems.length === 0 ? (
        <div className="empty-state">Nenhum evento oficial registrado ainda.</div>
      ) : (
        <div className="round-timeline-list">
          {visibleItems.map((item, index) => (
            <div
              key={`${item.kind || 'timeline'}-${item.eventHash || item.timestampUtc || index}-${item.eventType || index}`}
              className={`round-timeline-item round-timeline-item-${item.kind || 'unknown'}`}
            >
              <div className="round-timeline-main">
                <strong>{getTimelineLabel(item)}</strong>
                <span>{formatTime(item.timestampUtc, locale, timezone)}</span>
              </div>
              <div className="round-timeline-meta">
                {item.kind === 'round_event' ? (
                  <>
                    <span>Status: {item.roundStatus || '--'}</span>
                    {item.countValue != null && <span>Count: {item.countValue}</span>}
                    {item.reason && <span>Motivo: {item.reason}</span>}
                  </>
                ) : (
                  <>
                    {item.countBefore != null && item.countAfter != null && (
                      <span>Count: {item.countBefore} {'->'} {item.countAfter}</span>
                    )}
                    <span>Direcao: {item.direction || '--'}</span>
                    {item.lineId && <span>Linha: {item.lineId}</span>}
                    {item.streamProfileId && <span>Perfil: {item.streamProfileId}</span>}
                    {item.eventHash && <span>Hash: {String(item.eventHash).slice(0, 10)}...</span>}
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
