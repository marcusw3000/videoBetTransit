function getWinningMarkets(item) {
  if (!item.ranges?.length) return []

  const explicitWinners = item.ranges.filter((range) => range.isWinner)
  if (explicitWinners.length) return explicitWinners

  if (item.finalCount == null) return []
  return item.ranges.filter((range) => item.finalCount >= range.min && item.finalCount <= range.max)
}

function formatDate(iso) {
  if (!iso) return '--'
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function HistoryCard({ item, summary }) {
  const winners = getWinningMarkets(item)
  const cameraLabel = summary?.cameraIds?.length ? summary.cameraIds.join(', ') : 'Sem camera'
  const eventsCount = summary?.eventsCount ?? 0

  return (
    <div className="card history-card">
      <div className="history-main">
        <div className="history-id">{item.id}</div>
        <div className="history-meta">
          <span>{cameraLabel}</span>
          <span>{eventsCount} evento(s)</span>
        </div>
      </div>
      <div className="history-count">
        <span className="label">Total</span>
        <strong>{item.finalCount ?? '--'}</strong>
      </div>
      <div className="history-range">
        {winners.length ? (
          <span className="history-winner">{winners.map((winner) => `${winner.marketType === 'exact' ? `Exact ${winner.targetValue}` : winner.label} - ${winner.odds}x`).join(' | ')}</span>
        ) : '--'}
      </div>
      <div className="history-date">{formatDate(item.endsAt)}</div>
    </div>
  )
}
