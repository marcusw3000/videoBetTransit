function getArrow(item, overMarket) {
  if (!item || item.status === 'void') return { symbol: '○', cls: 'last-arrow-void' }

  const finalCount = item.finalCount
  if (finalCount == null) return { symbol: '○', cls: 'last-arrow-void' }

  if (overMarket) {
    return finalCount > overMarket.targetValue
      ? { symbol: '▲', cls: 'last-arrow-over' }
      : { symbol: '▼', cls: 'last-arrow-under' }
  }

  const overMkt = item.markets?.find((m) => m.marketType?.toLowerCase() === 'over')
  if (overMkt) {
    return finalCount > overMkt.targetValue
      ? { symbol: '▲', cls: 'last-arrow-over' }
      : { symbol: '▼', cls: 'last-arrow-under' }
  }

  return { symbol: '○', cls: 'last-arrow-void' }
}

export default function LastResults({ history = [], overMarket = null }) {
  const recent = history.slice(0, 6)

  return (
    <div className="last-results-bar">
      <span className="last-results-label">Últimos</span>
      <div className="last-results-arrows">
        {recent.map((item, i) => {
          const arrow = getArrow(item, overMarket)
          return (
            <span
              key={item.id || i}
              className={`last-arrow ${arrow.cls}`}
              title={item.finalCount != null ? `Total: ${item.finalCount}` : 'Anulado'}
            >
              {arrow.symbol}
            </span>
          )
        })}
        {recent.length === 0 && (
          <span className="last-results-empty">—</span>
        )}
      </div>
    </div>
  )
}
