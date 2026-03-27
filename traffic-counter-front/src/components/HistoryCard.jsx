function getWinningRange(item) {
  if (item.finalCount == null || !item.ranges?.length) return null
  return item.ranges.find(r => item.finalCount >= r.min && item.finalCount <= r.max)
}

function formatDate(iso) {
  if (!iso) return '–'
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function HistoryCard({ item }) {
  const winner = getWinningRange(item)

  return (
    <div className="card history-card">
      <div className="history-id">{item.id}</div>
      <div className="history-count">
        <span className="label">Total</span>
        <strong>{item.finalCount ?? '–'}</strong>
      </div>
      <div className="history-range">
        {winner ? (
          <span className="history-winner">{winner.label} · {winner.odds}x</span>
        ) : '–'}
      </div>
      <div className="history-date">{formatDate(item.endsAt)}</div>
    </div>
  )
}
