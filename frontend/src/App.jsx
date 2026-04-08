import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import AdminDashboard from './components/AdminDashboard'
import BettingPanel from './components/BettingPanel'
import LastResults from './components/LastResults'
import VideoPlayer from './components/VideoPlayer'
import { getCurrentRound, getRoundHistory } from './services/roundApi'
import { startRoundConnection, stopRoundConnection } from './services/roundSignalr'
import { getWorkerHealth } from './services/workerHealthApi'
import { getRoundPhase, getTimeLeftInSeconds, parseTimestampMs } from './utils/time'
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
  const created = parseTimestampMs(round.createdAt)
  const ends = parseTimestampMs(round.endsAt)
  if (Number.isNaN(created) || Number.isNaN(ends) || ends <= created) return null
  const minutes = Math.round((ends - created) / 60000)
  if (minutes <= 0) return null
  return `${minutes} ${minutes === 1 ? 'minuto' : 'minutos'}`
}

function LiveBadge({ phase, workerOnline = false }) {
  if (phase === 'loading' && workerOnline) {
    return <span className="live-badge live-badge-open"><span className="live-dot" />AO VIVO</span>
  }
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

function getAppView() {
  const params = new URLSearchParams(window.location.search)
  const queryView = params.get('view')
  const hashView = window.location.hash.replace('#', '')

  if (window.location.pathname.startsWith('/admin')) return 'admin'
  if (queryView === 'admin') return 'admin'
  if (hashView === 'admin') return 'admin'
  return 'market'
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
  const [workerHealth, setWorkerHealth] = useState(null)
  const roundIdRef = useRef('')

  const roundPhase = getRoundPhase(round)
  const betCloseSeconds = getTimeLeftInSeconds(round?.betCloseAt)
  const roundDurationLabel = getRoundDurationLabel(round)
  const markets = round?.markets || []
  const roundCount = round?.currentCount ?? null
  const workerOnline = Boolean(workerHealth?.ok || workerHealth?.streamConnected)
  const displayCount = roundCount
  const numericStakeAmount = Number.parseFloat(String(stakeAmount).replace(',', '.'))
  const hasValidStake = Number.isFinite(numericStakeAmount) && numericStakeAmount > 0

  const overMarket = useMemo(() => markets.find((m) => m.marketType?.toLowerCase() === 'over') || null, [markets])
  const recentHistory = useMemo(() => history.slice(0, RECENT_HISTORY_LIMIT), [history])

  const gameTitle = useMemo(() => {
    const name = getDisplayName(round)
    const dur = roundDurationLabel ? `(${roundDurationLabel})` : ''
    return `${name}${dur ? ' ' + dur : ''}: quantos carros?`
  }, [round, roundDurationLabel])
  const counterLabel = 'CONTAGEM DA RODADA'

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
      const data = await getCurrentRound(embedConfig.cameraId)
      updateRound(data)
      setError('')
    } catch (err) {
      console.error(err)
      setError('Falha ao carregar o round atual.')
    }
  }, [embedConfig.cameraId, updateRound])

  const loadHistory = useCallback(async () => {
    try {
      const data = await getRoundHistory(embedConfig.cameraId)
      setHistory(data)
    } catch (err) {
      console.error(err)
    }
  }, [embedConfig.cameraId])

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
          getCurrentRound(embedConfig.cameraId),
          getRoundHistory(embedConfig.cameraId),
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
  }, [embedConfig.cameraId, loadCurrentRound, loadHistory, updateRound])

  useEffect(() => {
    let active = true

    async function loadWorkerHealth() {
      try {
        const data = await getWorkerHealth()
        if (!active) return
        setWorkerHealth(data)
      } catch {
        if (!active) return
        setWorkerHealth(null)
      }
    }

    void loadWorkerHealth()
    const intervalId = setInterval(() => {
      void loadWorkerHealth()
    }, 2000)

    return () => {
      active = false
      clearInterval(intervalId)
    }
  }, [])

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
    const syncTimeLeft = () => {
      if (round?.endsAt) {
        setTimeLeftSeconds(getTimeLeftInSeconds(round.endsAt))
      } else {
        setTimeLeftSeconds(0)
      }
    }

    syncTimeLeft()
    const intervalId = setInterval(syncTimeLeft, 1000)
    return () => clearInterval(intervalId)
  }, [round])

  useEffect(() => {
    if (!round) return
    emitEmbedEvent('round-update', {
      roundId: round.roundId,
      status: round.status,
      isSuspended: round.isSuspended,
      currentCount: round.currentCount,
      displayCount,
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
  }, [displayCount, embedConfig, round])

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
            <LiveBadge phase={roundPhase} workerOnline={workerOnline} />
          </div>
        </div>
        <div className="header-right">
          <button
            type="button"
            className="header-link-btn"
            onClick={() => { window.location.href = '?view=admin' }}
          >
            Admin
          </button>
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
              <span className="count-bar-label">{counterLabel}</span>
              <span className="count-bar-value">
                {displayCount ?? '--'}
              </span>
            </div>
            <div className="count-bar-right">
              <span className="count-bar-label">TEMPO DO ROUND</span>
              <span className="count-bar-timer">
                {padTime(timeLeftSeconds / 60)}:{padTime(timeLeftSeconds % 60)}
              </span>
            </div>
          </div>

          <div className="video-wrapper">
            <VideoPlayer
              key={round?.roundId || 'live-player'}
              webrtcSrc={WEBRTC_URL}
              src={HLS_URL}
              fallbackSrc={MJPEG_URL}
              title={embedConfig.cameraLabel || 'Transmissão ao vivo'}
              countValue={displayCount}
            />
          </div>
        </div>

        {/* Right: betting panel */}
        <div className="right-panel">
          <BettingPanel
            markets={markets}
            roundPhase={roundPhase}
            betCloseSeconds={betCloseSeconds}
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
  const [view, setView] = useState(() => getAppView())

  useEffect(() => {
    const handleLocationChange = () => setView(getAppView())
    window.addEventListener('popstate', handleLocationChange)
    window.addEventListener('hashchange', handleLocationChange)
    return () => {
      window.removeEventListener('popstate', handleLocationChange)
      window.removeEventListener('hashchange', handleLocationChange)
    }
  }, [])

  return view === 'admin' ? <AdminDashboard /> : <MarketPage />
}
