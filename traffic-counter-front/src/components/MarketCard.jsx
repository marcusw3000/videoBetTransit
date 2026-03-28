function getMarketTitle(market) {
  switch ((market.marketType || '').toLowerCase()) {
    case 'under':
      return 'Under'
    case 'range':
      return 'Range'
    case 'over':
      return 'Over'
    case 'exact':
      return 'Exact'
    default:
      return market.label
  }
}

function getMarketDescription(market) {
  switch ((market.marketType || '').toLowerCase()) {
    case 'under':
      return `A contagem final precisa ficar abaixo de ${market.targetValue}.`
    case 'range':
      return `A contagem final precisa cair na faixa ${market.label}.`
    case 'over':
      return `A contagem final precisa ultrapassar ${market.targetValue}.`
    case 'exact':
      return `A contagem final precisa terminar exatamente em ${market.targetValue}.`
    default:
      return market.label
  }
}

function getMarketBadge(market, isActive, roundStatus) {
  if (market.isWinner === true) return { label: 'VENCEU', className: 'market-active-badge market-result-win' }
  if (market.isWinner === false && roundStatus === 'settled') return { label: 'NAO BATEU', className: 'market-active-badge market-result-lose' }
  if (roundStatus === 'closing') return { label: 'FECHADO', className: 'market-active-badge market-phase-closed' }
  if (roundStatus === 'settling') return { label: 'APURANDO', className: 'market-active-badge market-phase-settling' }
  if (isActive) return { label: 'AO VIVO', className: 'market-active-badge' }
  return null
}

export default function MarketCard({ market, isActive, roundStatus = 'open' }) {
  const marketType = (market.marketType || '').toLowerCase()
  const badge = getMarketBadge(market, isActive, roundStatus)

  return (
    <div className={`card market-card market-card-${marketType}${isActive ? ' market-card-active' : ''}`}>
      <div className="market-card-top">
        <h3>{getMarketTitle(market)}</h3>
        {market.targetValue != null && <span className="market-chip">Alvo {market.targetValue}</span>}
      </div>
      <p className="market-description">{getMarketDescription(market)}</p>
      <p className="market-odds">{market.odds}x payout</p>
      {badge && <span className={badge.className}>{badge.label}</span>}
    </div>
  )
}
