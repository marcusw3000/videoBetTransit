import { useMemo } from 'react'
import BetsHistory from './BetsHistory'

function formatCountdown(seconds) {
  const safe = Math.max(0, Math.floor(seconds || 0))
  const mm = String(Math.floor(safe / 60)).padStart(2, '0')
  const ss = String(safe % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

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
    case 'over': return 'mkt-pick-btn mkt-pick-over'
    case 'under': return 'mkt-pick-btn mkt-pick-under'
    case 'range': return 'mkt-pick-btn mkt-pick-range'
    case 'exact': return 'mkt-pick-btn mkt-pick-exact'
    default: return 'mkt-pick-btn mkt-pick-default'
  }
}


export default function BettingPanel({
  markets = [],
  roundPhase = 'open',
  betCloseSeconds = 0,
  selectedMarketId = '',
  onMarketSelect,
  onSubmitBet,
  stakeAmount = '3',
  onStakeChange,
  stakeOptions = [1, 10, 50, 100],
  locale = 'pt-BR',
  currency = 'BRL',
  isSuspended = false,
  pendingBet = null,
  isSubmittingBet = false,
}) {

  const numericStake = Number.parseFloat(String(stakeAmount).replace(',', '.'))
  const hasValidStake = Number.isFinite(numericStake) && numericStake > 0

  const selectedMarket = useMemo(
    () => markets.find((m) => (m.marketId || m.id) === selectedMarketId) || null,
    [markets, selectedMarketId],
  )

  const payout = hasValidStake && selectedMarket
    ? numericStake * Number(selectedMarket.odds ?? 1)
    : 0

  const isBettingOpen = roundPhase === 'open' && !isSuspended && !pendingBet
  const canBet = isBettingOpen && hasValidStake && !!selectedMarket

  function handleStakeIncrement(delta) {
    const next = Math.max(0, (hasValidStake ? numericStake : 0) + delta)
    onStakeChange?.(String(next % 1 === 0 ? next : next.toFixed(2)))
  }

  return (
    <div className="betting-panel">
      <div className="betting-panel-header">
        <div className="betting-panel-timer">
          <span className="betting-panel-timer-label">Apostas se encerram em</span>
          <strong className="betting-panel-timer-value">
            {roundPhase === 'open' ? formatCountdown(betCloseSeconds) : '00:00'}
          </strong>
        </div>
      </div>

      <div className="bet-type-tabs">
        <button
          type="button"
          className="bet-type-tab bet-type-tab-active"
        >
          Apostar
        </button>
        <span className="bet-type-refresh" title="Atualizar odds">R</span>
      </div>

      <div className="mkt-pick-grid">
        {markets.length === 0 && (
          <span className="mkt-pick-empty">Mercados indisponiveis</span>
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

      <details className="round-rules">
        <summary>Como funciona a rodada</summary>
        <p>As apostas encerram no horário indicado. A contagem continua até o fim da rodada, seguida da apuração. A próxima rodada depende da câmera estar pronta.</p>
        <p>O vídeo pode ter atraso. O contador e o resultado oficiais são informados pelo servidor. Os valores são simulados.</p>
        <p>Menos de exclui o limite; ou mais inclui o limite; entre inclui os dois extremos; exatamente exige igualdade.</p>
      </details>
      <div className="stake-section-panel">
        <div className="stake-section-header">
          <span className="stake-section-label">Quantia</span>
          <span className="stake-balance">Valor simulado</span>
        </div>

        <div className="stake-control-row">
          <button
            type="button"
            className="stake-stepper"
            onClick={() => handleStakeIncrement(-1)}
          >-</button>
          <div className="stake-display">
            <input
              type="number"
              aria-label="Valor da aposta simulada"
              min="0.01"
              max="10000"
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
            onClick={() => onStakeChange?.(String(stakeOptions[stakeOptions.length - 1]))}
          >
            Maior valor
          </button>
        </div>
      </div>

      {selectedMarket && hasValidStake && (
        <div className="payout-row">
          <div className="payout-label">
            <span>Para ganhar</span>
            <span className="payout-trophy">$</span>
          </div>
          <div className="payout-value-col">
            <span className="payout-amount">{formatCurrency(payout, locale, currency)}</span>
            <span className="payout-sub">{formatOdds(selectedMarket.odds, locale)}x</span>
          </div>
        </div>
      )}

      <button
        type="button"
        className={`bet-cta-btn${canBet ? ' bet-cta-btn-active' : ''}`}
        disabled={!canBet || isSubmittingBet}
        onClick={() => canBet && onSubmitBet?.(selectedMarket)}
      >
        {isSubmittingBet
          ? 'Enviando aposta...'
          : !isBettingOpen
            ? roundPhase === 'closing' ? 'Mercado Fechado' : 'Aguardando Round'
            : !hasValidStake
              ? 'Escolha o valor da aposta'
              : !selectedMarket
                ? 'Escolha um mercado'
                : `Comprar ${selectedMarket.label || selectedMarket.marketType}`}
      </button>

      {pendingBet && <div role="status" className="pending-bet">
        <p>A confirmacao da tentativa anterior esta pendente. Ela sera reenviada com o mesmo identificador.</p>
        <button disabled={isSubmittingBet} onClick={() => onSubmitBet?.()}>Confirmar tentativa</button>
      </div>}
      <BetsHistory locale={locale} />
    </div>
  )
}
