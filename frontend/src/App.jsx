import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import BettingPanel from './components/BettingPanel'
import LastResults from './components/LastResults'
import VideoPlayer from './components/VideoPlayer'
import { getCurrentRound, getRoundHistory } from './services/roundApi'
import { startRoundConnection, stopRoundConnection } from './services/roundSignalr'
import { getRoundPhase, getTimeLeftInSeconds } from './utils/time'
import { WEBRTC_URL, HLS_URL, MJPEG_URL } from './config'
import { applyEmbedTheme, EMBED_CONFIG_EVENT, emitEmbedEvent, getEmbedConfig } from './embed'

const RECENT_HISTORY_LIMIT = 6

function formatCurrency(value, locale, currency) {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

function formatOdds(odds, locale = 'pt-BR') {
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(odds ?? 0))
}

function padTime(n) {
  return String(Math.max(0, Math.floor(n))).padStart(2, '0')
}

function getDisplayName(round) {
  return round?.displayName || 'Rodada Turbo'
}

function getRoundDurationLabel(round) {
  if (!round?.createdAt || !round?.endsAt) return null
  const created = new Date(round.createdAt).getTime()
  const ends = new Date(round.endsAt).getTime()
  if (Number.isNaN(created) || Number.isNaN(ends) || ends <= created) return null
  const minutes = Math.round((ends - created) / 60000)
  if (minutes <= 0) return null
  return `${minutes} ${minutes === 1 ? 'minuto' : 'minutos'}`
}

function LiveBadge({ phase }) {
  if (phase === 'open') {
    return <span className="live-badge live-badge-open"><span className="live-dot" />AO VIVO</span>
  }
  if (phase === 'closing') {
    return <span className="live-badge live-badge-closing">FECHADO</span>
  }
  if (phase === 'settling') {
    return <span className="live-badge live-badge-settling">APURANDO</span>
  }
  if (phase === 'settled') {
    return <span className="live-badge live-badge-settled">ENCERRADO</span>
  }
  if (phase === 'void') {
    return <span className="live-badge live-badge-void">ANULADO</span>
  }
  return <span className="live-badge">CARREGANDO</span>
}

function MarketPage() {
  const [embedConfig, setEmbedConfig] = useState(() => getEmbedConfig())
  const [round, setRound] = useState(null)
  const [history, setHistory] = useState([])
  const [timeLeftSeconds, setTimeLeftSeconds] = useState(0)
  const [error, setError] = useState('')
  const [toast, setToast] = useState(null)
  const [selectedMarketId, setSelectedMarketId] = useState('')
  const [stakeAmount, setStakeAmount] = useState(() => String(getEmbedConfig().defaultStake))
  const roundIdRef = useRef('')

  const roundPhase = getRoundPhase(round)
  const betCloseSeconds = getTimeLeftInSeconds(round?.betCloseAt)
  const roundDurationLabel = getRoundDurationLabel(round)
  const markets = round?.markets || []
  const numericStakeAmount = Number.parseFloat(String(stakeAmount).replace(',', '.'))
  const hasValidStake = Number.isFinite(numericStakeAmount) && numericStakeAmount > 0

  const headerTimerSeconds = roundPhase === 'open' ? betCloseSeconds : timeLeftSeconds
  const headerMins = padTime(headerTimerSeconds / 60)
  const headerSecs = padTime(headerTimerSeconds % 60)

  const betCloseMins = padTime(betCloseSeconds / 60)
  const betCloseSecs = padTime(betCloseSeconds % 60)

  const overMarket = useMemo(() => markets.find((m) => m.marketType?.toLowerCase() === 'over') || null, [markets])
  const recentHistory = useMemo(() => history.slice(0, RECENT_HISTORY_LIMIT), [history])

  const gameTitle = useMemo(() => {
    const name = getDisplayName(round)
    const dur = roundDurationLabel ? `(${roundDurationLabel})` : ''
    return `${name}${dur ? ' ' + dur : ''}: quantos carros?`
  }, [round, roundDurationLabel])

  function showToast(message) {
    const id = Date.now()
    setToast({ message, id })
    setTimeout(() => setToast((t) => (t?.id === id ? null : t)), 4000)
  }

  const updateRound = useCallback((nextRound) => {
    const nextRoundId = nextRound?.roundId || ''
    if (roundIdRef.current && nextRoundId && roundIdRef.current !== nextRoundId) {
      setSelectedMarketId('')
    }
    roundIdRef.current = nextRoundId
    setRound(nextRound)
  }, [])

  const loadCurrentRound = useCallback(async () => {
    try {
      const data = await getCurrentRound()
      updateRound(data)
      setError('')
    } catch (err) {
      console.error(err)
      setError('Falha ao carregar o round atual.')
    }
  }, [updateRound])

  const loadHistory = useCallback(async () => {
    try {
      const data = await getRoundHistory()
      setHistory(data)
    } catch (err) {
      console.error(err)
    }
  }, [])

  function handleMarketSelect(market) {
    if (!round) return
    if (!hasValidStake) {
      showToast('Escolha um valor de aposta válido antes de selecionar o mercado.')
      return
    }
    setSelectedMarketId(market.marketId || market.id)
    emitEmbedEvent('market-select', {
      marketId: market.marketId || market.id,
      marketType: market.marketType,
      marketLabel: market.label,
      odds: market.odds,
      stakeAmount: numericStakeAmount,
      formattedStake: formatCurrency(numericStakeAmount, embedConfig.locale, embedConfig.currency),
      targetValue: market.targetValue,
      roundId: round.roundId,
      roundStatus: round.status,
      displayName: round.displayName,
      betCloseAt: round.betCloseAt,
      endsAt: round.endsAt,
      cameraId: embedConfig.cameraId,
      cameraLabel: embedConfig.cameraLabel,
      currency: embedConfig.currency,
      locale: embedConfig.locale,
      timezone: embedConfig.timezone,
    }, embedConfig)
  }

  useEffect(() => {
    let active = true

    async function bootstrap() {
      try {
        const [currentRound, roundHistory] = await Promise.all([
          getCurrentRound(),
          getRoundHistory(),
        ])
        if (!active) return
        updateRound(currentRound)
        setHistory(roundHistory)
        setError('')
      } catch (err) {
        if (!active) return
        console.error(err)
        setError('Falha ao carregar os dados iniciais.')
      }
    }

    void bootstrap()

    startRoundConnection({
      onCountUpdated: (data) => {
        if (!active) return
        updateRound(data)
      },
      onRoundSettled: async () => {
        if (!active) return
        setSelectedMarketId('')
        showToast('Round encerrado! Novo round iniciado.')
        await loadCurrentRound()
        await loadHistory()
      },
    }).catch((err) => {
      if (!active) return
      console.error(err)
      setError('Falha ao conectar em tempo real.')
    })

    return () => {
      active = false
      stopRoundConnection().catch(console.error)
    }
  }, [loadCurrentRound, loadHistory, updateRound])

  useEffect(() => {
    const handleConfigUpdate = () => {
      const nextConfig = getEmbedConfig()
      setEmbedConfig(nextConfig)
      setStakeAmount(String(nextConfig.defaultStake))
    }
    window.addEventListener(EMBED_CONFIG_EVENT, handleConfigUpdate)
    return () => window.removeEventListener(EMBED_CONFIG_EVENT, handleConfigUpdate)
  }, [])

  useEffect(() => {
    applyEmbedTheme(embedConfig)
    document.title = `${embedConfig.brand} | ${embedConfig.cameraLabel}`
    emitEmbedEvent('ready', {
      brand: embedConfig.brand,
      locale: embedConfig.locale,
      cameraId: embedConfig.cameraId,
      cameraLabel: embedConfig.cameraLabel,
      currency: embedConfig.currency,
      timezone: embedConfig.timezone,
      stakeOptions: embedConfig.stakeOptions,
      defaultStake: embedConfig.defaultStake,
      mode: embedConfig.mode,
    }, embedConfig)
  }, [embedConfig])

  useEffect(() => {
    const intervalId = setInterval(() => {
      if (round?.endsAt) {
        setTimeLeftSeconds(getTimeLeftInSeconds(round.endsAt))
      } else {
        setTimeLeftSeconds(0)
      }
    }, 1000)
    return () => clearInterval(intervalId)
  }, [round])

  useEffect(() => {
    if (!round) return
    emitEmbedEvent('round-update', {
      roundId: round.roundId,
      status: round.status,
      isSuspended: round.isSuspended,
      currentCount: round.currentCount,
      createdAt: round.createdAt,
      betCloseAt: round.betCloseAt,
      endsAt: round.endsAt,
      settledAt: round.settledAt,
      voidedAt: round.voidedAt,
      voidReason: round.voidReason,
      finalCount: round.finalCount,
      markets: round.markets,
      cameraId: embedConfig.cameraId,
    }, embedConfig)
  }, [embedConfig, round])

  useEffect(() => {
    if (!hasValidStake) return
    emitEmbedEvent('stake-change', {
      stakeAmount: numericStakeAmount,
      formattedStake: formatCurrency(numericStakeAmount, embedConfig.locale, embedConfig.currency),
      currency: embedConfig.currency,
      locale: embedConfig.locale,
    }, embedConfig)
  }, [embedConfig, hasValidStake, numericStakeAmount])

  return (
    <div className="page">
    <div className="page-inner">
      {/* ── Header ── */}
      <header className="exchange-header">
        <div className="header-left">
          <div className="header-brand-icon" aria-label="brand icon">🚗</div>
          <div className="header-title-block">
            <span className="header-game-title">{gameTitle}</span>
            <LiveBadge phase={roundPhase} />
          </div>
        </div>
        <div className="header-right">
          <div className="header-timer-block">
            <div className="header-timer-digits">
              <span className="header-timer-num">{headerMins}</span>
              <span className="header-timer-sep">:</span>
              <span className="header-timer-num">{headerSecs}</span>
            </div>
            <div className="header-timer-labels">
              <span>MINS</span>
              <span>SECS</span>
            </div>
          </div>
        </div>
      </header>

      {/* ── Last results bar ── */}
      <div className="recents-bar">
        <LastResults history={recentHistory} overMarket={overMarket} />
      </div>

      {error && <div className="error-banner">{error}</div>}
      {toast && <div className="toast" key={toast.id}>{toast.message}</div>}

      {/* ── Main body ── */}
      <div className="exchange-body">
        {/* Left: video + count */}
        <div className="left-panel">
          <div className="count-bar">
            <div className="count-bar-left">
              <span className="count-bar-label">CONTAGEM ATUAL</span>
              <span className="count-bar-value">
                {round?.currentCount ?? '--'}
              </span>
            </div>
            <div className="count-bar-right">
              <span className="count-bar-label">PREVISÕES ENCERRAM EM</span>
              <span className="count-bar-timer">{betCloseMins}:{betCloseSecs}</span>
            </div>
          </div>

          <div className="video-wrapper">
            <VideoPlayer
              key={round?.roundId || 'live-player'}
              webrtcSrc={WEBRTC_URL}
              src={HLS_URL}
              fallbackSrc={MJPEG_URL}
              title={embedConfig.cameraLabel || 'Transmissão ao vivo'}
              countValue={round?.currentCount}
            />
          </div>
        </div>

        {/* Right: betting panel */}
        <div className="right-panel">
          <BettingPanel
            markets={markets}
            roundPhase={roundPhase}
            selectedMarketId={selectedMarketId}
            onMarketSelect={handleMarketSelect}
            stakeAmount={stakeAmount}
            onStakeChange={setStakeAmount}
            stakeOptions={embedConfig.stakeOptions}
            locale={embedConfig.locale}
            currency={embedConfig.currency}
            balance={0}
            isSuspended={round?.isSuspended}
          />
        </div>
      </div>

      {/* ── Bottom market bar ── */}
      {markets.length > 0 && (
        <div className="bottom-market-bar">
          {markets.map((m) => {
            const mId = m.marketId || m.id
            const isSelected = mId === selectedMarketId
            const type = (m.marketType || '').toLowerCase()
            return (
              <button
                key={mId}
                type="button"
                className={`bottom-mkt-btn bottom-mkt-btn-${type}${isSelected ? ' bottom-mkt-btn-selected' : ''}`}
                onClick={() => handleMarketSelect(m)}
                disabled={roundPhase !== 'open' || round?.isSuspended}
              >
                {m.label || m.marketType} ({formatOdds(m.odds, embedConfig.locale)}x)
              </button>
            )
          })}
        </div>
      )}
    </div>
    </div>
  )
}

export default function App() {
  return <MarketPage />
}
