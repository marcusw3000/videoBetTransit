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
      return `Você vence se o total oficial terminar abaixo de ${market.targetValue}.`
    case 'range':
      return `Você vence se o total oficial terminar na faixa ${market.label}.`
    case 'over':
      return `Você vence se o total oficial terminar acima de ${market.targetValue}.`
    case 'exact':
      return `Você vence se o total oficial terminar exatamente em ${market.targetValue}.`
    default:
      return market.label
  }
}

function getMarketBadge(market, isActive, roundStatus, isSelected) {
  if (market.isWinner === true) return { label: 'VENCEU', className: 'market-active-badge market-result-win' }
  if (market.isWinner === false && roundStatus === 'settled') return { label: 'NÃO BATEU', className: 'market-active-badge market-result-lose' }
  if (isSelected && roundStatus === 'open') return { label: 'SELECIONADO', className: 'market-active-badge market-selected-badge' }
  if (roundStatus === 'closing') return { label: 'FECHADO', className: 'market-active-badge market-phase-closed' }
  if (roundStatus === 'settling') return { label: 'APURANDO', className: 'market-active-badge market-phase-settling' }
  if (roundStatus === 'void') return { label: 'ANULADO', className: 'market-active-badge market-phase-settling' }
  if (isActive) return { label: 'AO VIVO', className: 'market-active-badge' }
  return null
}

function formatOdds(odds, locale = 'pt-BR') {
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(odds ?? 0))
}

export default function MarketCard({
  market,
  isActive,
  roundStatus = 'open',
  onSelect,
  isSelected = false,
  locale = 'pt-BR',
  isSuspended = false,
  requiresStake = false,
}) {
  const marketType = (market.marketType || '').toLowerCase()
  const badge = getMarketBadge(market, isActive, roundStatus, isSelected)
  const canSelect = typeof onSelect === 'function' && roundStatus === 'open' && !isSuspended && !requiresStake

  function handleClick() {
    if (!canSelect) return
    onSelect(market)
  }

  return (
    <button
      type="button"
      className={`card market-card market-card-${marketType}${isActive ? ' market-card-active' : ''}${canSelect ? ' market-card-selectable' : ''}${isSelected ? ' market-card-selected' : ''}`}
      onClick={handleClick}
      disabled={!canSelect}
    >
      <div className="market-card-top">
        <h3>{getMarketTitle(market)}</h3>
        {market.targetValue != null && <span className="market-chip">Linha {market.targetValue}</span>}
      </div>
      <p className="market-description">{getMarketDescription(market)}</p>
      <p className="market-odds">Odds {formatOdds(market.odds, locale)}</p>
      {badge && <span className={badge.className}>{badge.label}</span>}
      <span className="market-cta">
        {requiresStake ? 'Escolha o valor da aposta' : roundStatus === 'open' ? 'Adicionar ao betslip' : roundStatus === 'closing' ? 'Mercado fechado' : roundStatus === 'settling' ? 'Resultado em apuração' : roundStatus === 'settled' ? 'Resultado oficial' : 'Mercado indisponível'}
      </span>
    </button>
  )
}
