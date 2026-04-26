function getWinningMarkets(item) {
  if (!item.markets?.length) return []

  const explicitWinners = item.markets.filter((range) => range.isWinner)
  if (explicitWinners.length) return explicitWinners

  if (item.finalCount == null) return []
  return item.markets.filter((range) => item.finalCount >= range.min && item.finalCount <= range.max)
}

function formatDate(iso, locale = 'pt-BR', timezone = 'America/Sao_Paulo') {
  if (!iso) return '--'
  try {
    return new Date(iso).toLocaleString(locale, {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: timezone,
    })
  } catch {
    return new Date(iso).toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  }
}

function getHistoryStatusLabel(item) {
  switch ((item.status || '').toLowerCase()) {
    case 'settled':
      return 'Encerrada'
    case 'void':
      return 'Anulada'
    default:
      return item.status || '--'
  }
}

export default function HistoryCard({
  item,
  locale = 'pt-BR',
  timezone = 'America/Sao_Paulo',
}) {
  const winners = getWinningMarkets(item)
  const cameraLabel = item.cameraIds?.length ? item.cameraIds.join(', ') : 'Sem câmera'
  const eventsCount = item.eventsCount ?? 0

  return (
    <div className="card history-card">
      <div className="history-main">
        <div className="history-id">{item.id}</div>
        <div className="history-meta">
          <span>{item.displayName || 'Rodada Normal'}</span>
          <span>Modo: Normal</span>
          <span>{cameraLabel}</span>
          <span>{eventsCount} evento(s)</span>
          <span>{getHistoryStatusLabel(item)}</span>
        </div>
      </div>
      <div className="history-count">
        <span className="label">Total</span>
        <strong>{item.finalCount ?? '--'}</strong>
      </div>
      <div className="history-range">
        {item.status === 'void' ? (
          <span className="history-winner">{item.voidReason || 'Round anulado'}</span>
        ) : winners.length ? (
          <span className="history-winner">{winners.map((winner) => `${winner.marketType === 'exact' ? `Exact ${winner.targetValue}` : winner.label} - ${winner.odds}x`).join(' | ')}</span>
        ) : '--'}
      </div>
      <div className="history-date">{formatDate(item.settledAt || item.voidedAt || item.endsAt, locale, timezone)}</div>
    </div>
  )
}
