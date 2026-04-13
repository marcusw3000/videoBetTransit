function resolveOverMarket(item, fallbackOverMarket) {
  return item?.markets?.find((market) => market.marketType?.toLowerCase() === 'over') || fallbackOverMarket || null
}

function getArrow(item, fallbackOverMarket) {
  if (!item || item.status === 'void') return { symbol: '\u25cb', cls: 'last-arrow-void' }

  const finalCount = item.finalCount
  if (finalCount == null) return { symbol: '\u25cb', cls: 'last-arrow-void' }

  const overMarket = resolveOverMarket(item, fallbackOverMarket)
  if (overMarket?.targetValue != null) {
    return finalCount >= overMarket.targetValue
      ? { symbol: '\u25b2', cls: 'last-arrow-over' }
      : { symbol: '\u25bc', cls: 'last-arrow-under' }
  }

  return { symbol: '\u25cb', cls: 'last-arrow-void' }
}

export default function LastResults({ history = [], overMarket = null }) {
  const recent = history.slice(0, 6)

  return (
    <div className="last-results-bar">
      <span className="last-results-label">{'\u00daltimos'}</span>
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
          <span className="last-results-empty">{'\u2014'}</span>
        )}
      </div>
    </div>
  )
}
