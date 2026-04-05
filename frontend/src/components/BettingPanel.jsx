import { useMemo, useState } from 'react'

function formatOdds(odds, locale = 'pt-BR') {
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(odds ?? 0))
}

function formatCurrency(value, locale, currency) {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

function getMarketBtnClass(marketType) {
  switch ((marketType || '').toLowerCase()) {
    case 'over':  return 'mkt-pick-btn mkt-pick-over'
    case 'under': return 'mkt-pick-btn mkt-pick-under'
    case 'range': return 'mkt-pick-btn mkt-pick-range'
    case 'exact': return 'mkt-pick-btn mkt-pick-exact'
    default:      return 'mkt-pick-btn mkt-pick-default'
  }
}

const POSITIONS_TABS = ['Posições', 'Em aberto', 'Encerrados']

export default function BettingPanel({
  markets = [],
  roundPhase = 'open',
  selectedMarketId = '',
  onMarketSelect,
  stakeAmount = '3',
  onStakeChange,
  stakeOptions = [1, 10, 50, 100],
  locale = 'pt-BR',
  currency = 'BRL',
  balance = 0,
  isSuspended = false,
}) {
  const [activeTab, setActiveTab] = useState('Comprar')
  const [posTab, setPosTab] = useState('Posições')

  const betTabs = ['Comprar', 'Vender', 'A mercado']

  const numericStake = Number.parseFloat(String(stakeAmount).replace(',', '.'))
  const hasValidStake = Number.isFinite(numericStake) && numericStake > 0

  const selectedMarket = useMemo(
    () => markets.find((m) => (m.marketId || m.id) === selectedMarketId) || null,
    [markets, selectedMarketId]
  )

  const payout = hasValidStake && selectedMarket
    ? numericStake * Number(selectedMarket.odds ?? 1)
    : 0

  const isBettingOpen = roundPhase === 'open' && !isSuspended
  const canBet = isBettingOpen && hasValidStake && !!selectedMarket

  function handleStakeIncrement(delta) {
    const next = Math.max(0, (hasValidStake ? numericStake : 0) + delta)
    onStakeChange?.(String(next % 1 === 0 ? next : next.toFixed(2)))
  }

  return (
    <div className="betting-panel">

      {/* Panel header */}
      <div className="betting-panel-header">
        {selectedMarket ? (
          <div className="betting-panel-title">
            <span className={`panel-mkt-dot panel-mkt-dot-${(selectedMarket.marketType || '').toLowerCase()}`} />
            <span className="panel-mkt-name">{selectedMarket.label || selectedMarket.marketType}</span>
          </div>
        ) : (
          <span className="panel-mkt-placeholder">Escolha um mercado</span>
        )}
      </div>

      {/* Bet type tabs */}
      <div className="bet-type-tabs">
        {betTabs.map((tab) => (
          <button
            key={tab}
            type="button"
            className={`bet-type-tab${activeTab === tab ? ' bet-type-tab-active' : ''}${tab !== 'Comprar' ? ' bet-type-tab-disabled' : ''}`}
            onClick={() => tab === 'Comprar' && setActiveTab(tab)}
            disabled={tab !== 'Comprar'}
          >
            {tab}
          </button>
        ))}
        <span className="bet-type-refresh" title="Atualizar odds">↻</span>
      </div>

      {/* Market pick buttons */}
      <div className="mkt-pick-grid">
        {markets.length === 0 && (
          <span className="mkt-pick-empty">Mercados indisponíveis</span>
        )}
        {markets.map((m) => {
          const mId = m.marketId || m.id
          const isSelected = mId === selectedMarketId
          return (
            <button
              key={mId}
              type="button"
              className={`${getMarketBtnClass(m.marketType)}${isSelected ? ' mkt-pick-selected' : ''}${!isBettingOpen ? ' mkt-pick-disabled' : ''}`}
              onClick={() => isBettingOpen && onMarketSelect?.(m)}
              disabled={!isBettingOpen}
            >
              <span className="mkt-pick-label">{m.label || m.marketType}</span>
              <span className="mkt-pick-odds">({formatOdds(m.odds, locale)}x)</span>
            </button>
          )
        })}
      </div>

      {/* Stake section */}
      <div className="stake-section-panel">
        <div className="stake-section-header">
          <span className="stake-section-label">Quantia</span>
          <span className="stake-balance">Saldo: {formatCurrency(balance, locale, currency)}</span>
        </div>

        <div className="stake-control-row">
          <button
            type="button"
            className="stake-stepper"
            onClick={() => handleStakeIncrement(-1)}
          >−</button>
          <div className="stake-display">
            <input
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              className="stake-display-input"
              value={stakeAmount}
              onChange={(e) => onStakeChange?.(e.target.value)}
            />
          </div>
          <button
            type="button"
            className="stake-stepper"
            onClick={() => handleStakeIncrement(1)}
          >+</button>
        </div>

        <div className="stake-chips-row">
          {stakeOptions.map((opt) => (
            <button
              key={opt}
              type="button"
              className={`stake-chip-panel${numericStake === opt ? ' stake-chip-panel-active' : ''}`}
              onClick={() => onStakeChange?.(String(opt))}
            >
              {opt}
            </button>
          ))}
          <button
            type="button"
            className="stake-chip-panel"
            onClick={() => onStakeChange?.(String(balance > 0 ? balance : stakeOptions[stakeOptions.length - 1]))}
          >
            MAX
          </button>
        </div>
      </div>

      {/* Payout */}
      {selectedMarket && hasValidStake && (
        <div className="payout-row">
          <div className="payout-label">
            <span>Para ganhar</span>
            <span className="payout-trophy">🏆</span>
          </div>
          <div className="payout-value-col">
            <span className="payout-amount">{formatCurrency(payout, locale, currency)}</span>
            <span className="payout-sub">{formatOdds(selectedMarket.odds, locale)}x</span>
          </div>
        </div>
      )}

      {/* CTA button */}
      <button
        type="button"
        className={`bet-cta-btn${canBet ? ' bet-cta-btn-active' : ''}`}
        disabled={!canBet}
      >
        {!isBettingOpen
          ? roundPhase === 'closing' ? 'Mercado Fechado' : 'Aguardando Round'
          : !hasValidStake
          ? 'Escolha o valor da aposta'
          : !selectedMarket
          ? 'Escolha um mercado'
          : `Comprar ${selectedMarket.label || selectedMarket.marketType}`}
      </button>

      {/* Positions section */}
      <div className="positions-section">
        <span className="positions-title">Minhas posições</span>
        <div className="positions-tabs">
          {POSITIONS_TABS.map((t) => (
            <button
              key={t}
              type="button"
              className={`positions-tab${posTab === t ? ' positions-tab-active' : ''}`}
              onClick={() => setPosTab(t)}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="positions-empty">
          Faça login para visualizar suas posições.
        </div>
      </div>
    </div>
  )
}
