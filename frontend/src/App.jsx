import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import AdminDashboard from './components/AdminDashboard'
import BettingPanel from './components/BettingPanel'
import DetectionsList from './components/DetectionsList'
import HistoryDropdown from './components/HistoryDropdown'
import LastResults from './components/LastResults'
import VideoPlayer from './components/VideoPlayer'
import { placeBet } from './services/betApi'
import { getCurrentRound, getRoundHistory } from './services/roundApi'
import { startRoundConnection, stopRoundConnection } from './services/roundSignalr'
import { getWorkerHealth } from './services/workerHealthApi'
import { getRoundPhase, getTimeLeftInSeconds, parseTimestampMs } from './utils/time'
import { buildHlsUrlFromPath, buildMjpegUrl, buildWebRtcWrapperUrlFromPath } from './config'
import { applyEmbedTheme, EMBED_CONFIG_EVENT, emitEmbedEvent, getEmbedConfig } from './embed'

const RECENT_HISTORY_LIMIT = 6
const ROUND_POLL_INTERVAL_MS = 3000

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

function buildTransactionId() {
  if (window.crypto?.randomUUID) return `tx_${window.crypto.randomUUID()}`
  return `tx_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
}

function getApiErrorMessage(error, fallback) {
  return error?.response?.data?.error || fallback
}

function reconcileBetWithRound(bet, roundData) {
  if (!bet || !roundData || bet.roundId !== roundData.roundId) return bet

  if (roundData.status === 'void') {
    return {
      ...bet,
      status: 'void',
      voidedAt: roundData.voidedAt || new Date().toISOString(),
    }
  }

  if (roundData.status !== 'settled') return bet

  const winningMarket = (roundData.markets || []).find((market) => market.marketId === bet.marketId)
  return {
    ...bet,
    status: winningMarket?.isWinner ? 'settled_win' : 'settled_loss',
    settledAt: roundData.settledAt || new Date().toISOString(),
  }
}

function getDisplayName(round) {
  return round?.displayName || 'Rodada Normal'
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

function isRoundForCamera(round, cameraId) {
  const expected = String(cameraId || '').trim().toLowerCase()
  if (!expected) return true

  const directCameraId = String(round?.cameraId || '').trim().toLowerCase()
  if (directCameraId) return directCameraId === expected

  const cameraIds = Array.isArray(round?.cameraIds)
    ? round.cameraIds.map((item) => String(item || '').trim().toLowerCase()).filter(Boolean)
    : []

  return cameraIds.length === 0 || cameraIds.includes(expected)
}

function isRoundForPipeline(round, cameraIds) {
  const allowed = Array.isArray(cameraIds)
    ? cameraIds.map((item) => String(item || '').trim().toLowerCase()).filter(Boolean)
    : []

  if (allowed.length === 0) return true

  const directCameraId = String(round?.cameraId || '').trim().toLowerCase()
  if (directCameraId) return allowed.includes(directCameraId)

  const roundCameraIds = Array.isArray(round?.cameraIds)
    ? round.cameraIds.map((item) => String(item || '').trim().toLowerCase()).filter(Boolean)
    : []

  return roundCameraIds.some((item) => allowed.includes(item))
}

function filterHistoryByPipelineCameras(history, cameraIds) {
  const allowed = Array.isArray(cameraIds)
    ? cameraIds.map((item) => String(item || '').trim().toLowerCase()).filter(Boolean)
    : []

  if (allowed.length === 0) return Array.isArray(history) ? history : []

  return (Array.isArray(history) ? history : []).filter((item) => {
    const cameraId = String(item?.cameraId || '').trim().toLowerCase()
    return cameraId && allowed.includes(cameraId)
  })
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
  const [recentBets, setRecentBets] = useState([])
  const [isSubmittingBet, setIsSubmittingBet] = useState(false)
  const [workerHealth, setWorkerHealth] = useState(null)
  const roundIdRef = useRef('')

  const roundPhase = getRoundPhase(round)
  const isTurboRound = String(round?.roundMode || 'normal').toLowerCase() === 'turbo'
  const betCloseSeconds = getTimeLeftInSeconds(round?.betCloseAt)
  const roundDurationLabel = getRoundDurationLabel(round)
  const markets = round?.markets || []
  const roundCount = round?.currentCount ?? null
  const workerOnline = Boolean(workerHealth?.ok || workerHealth?.streamConnected)
  const displayCount = roundCount
  const numericStakeAmount = Number.parseFloat(String(stakeAmount).replace(',', '.'))
  const hasValidStake = Number.isFinite(numericStakeAmount) && numericStakeAmount > 0

  const overMarket = useMemo(() => markets.find((m) => m.marketType?.toLowerCase() === 'over') || null, [markets])
  const selectedMarket = useMemo(
    () => markets.find((market) => (market.marketId || market.id) === selectedMarketId) || null,
    [markets, selectedMarketId],
  )
  const filteredHistory = useMemo(
    () => filterHistoryByPipelineCameras(history, workerHealth?.streamProfileCameraIds),
    [history, workerHealth?.streamProfileCameraIds],
  )
  const cameraActivation = workerHealth?.cameraActivation || null
  const pipelineCameraIds = useMemo(
    () => (Array.isArray(workerHealth?.streamProfileCameraIds) ? workerHealth.streamProfileCameraIds : []),
    [workerHealth?.streamProfileCameraIds],
  )
  const recentHistory = useMemo(() => filteredHistory.slice(0, RECENT_HISTORY_LIMIT), [filteredHistory])
  const isCameraTransitioning = Boolean(cameraActivation && cameraActivation.phase !== 'ready')
  const roundCameraId = cameraActivation?.readyCameraId || workerHealth?.cameraId || embedConfig.cameraId
  const activeStreamPath = cameraActivation?.readyProcessedStreamPath || workerHealth?.processedStreamPath || ''
  const activeCameraId = roundCameraId
  const activeCameraLabel = cameraActivation?.readyProfileLabel || workerHealth?.streamRotation?.activeProfileLabel || embedConfig.cameraLabel
  const transitionCameraLabel = cameraActivation?.requestedProfileLabel || workerHealth?.streamRotation?.activeProfileLabel || activeCameraLabel
  const webrtcSrc = useMemo(
    () => buildWebRtcWrapperUrlFromPath(activeStreamPath, activeCameraId),
    [activeCameraId, activeStreamPath],
  )
  const hlsSrc = useMemo(
    () => buildHlsUrlFromPath(activeStreamPath, activeCameraId),
    [activeCameraId, activeStreamPath],
  )
  const mjpegSrc = useMemo(() => buildMjpegUrl(), [])

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
      const data = await getCurrentRound(activeCameraId)
      updateRound(data)
      setError('')
    } catch (err) {
      console.error(err)
      setError('Falha ao carregar o round atual.')
    }
  }, [activeCameraId, updateRound])

  const loadHistory = useCallback(async () => {
    try {
      const data = await getRoundHistory()
      setHistory(data)
    } catch (err) {
      console.error(err)
    }
  }, [])

  const reconcileRecentBets = useCallback((roundData) => {
    setRecentBets((current) => current.map((bet) => reconcileBetWithRound(bet, roundData)))
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
      cameraId: activeCameraId,
      cameraLabel: activeCameraLabel,
      currency: embedConfig.currency,
      locale: embedConfig.locale,
      timezone: embedConfig.timezone,
    }, embedConfig)
  }

  async function handleSubmitBet() {
    if (!round || !selectedMarket || !hasValidStake || roundPhase !== 'open' || round?.isSuspended) {
      return
    }

    const transactionId = buildTransactionId()
    const payload = {
      transactionId,
      gameSessionId: embedConfig.gameSessionId,
      roundId: round.roundId,
      marketId: selectedMarket.marketId || selectedMarket.id,
      stakeAmount: numericStakeAmount,
      currency: embedConfig.currency,
      playerRef: embedConfig.playerRef || null,
      operatorRef: embedConfig.operatorRef || null,
      metadataJson: JSON.stringify({
        cameraId: activeCameraId,
        cameraLabel: activeCameraLabel,
        locale: embedConfig.locale,
      }),
    }

    emitEmbedEvent('bet-submit', {
      transactionId,
      ...payload,
      marketLabel: selectedMarket.label,
      odds: selectedMarket.odds,
    }, embedConfig)

    try {
      setIsSubmittingBet(true)
      const acceptedBet = await placeBet(payload)
      setRecentBets((current) => [acceptedBet, ...current.filter((bet) => bet.id !== acceptedBet.id)].slice(0, 8))
      setSelectedMarketId('')
      showToast(`Aposta aceita: ${selectedMarket.label}.`)
      emitEmbedEvent('bet-accepted', acceptedBet, embedConfig)
    } catch (err) {
      const message = getApiErrorMessage(err, 'Nao foi possivel concluir a aposta.')
      showToast(message)
      emitEmbedEvent('bet-rejected', {
        transactionId,
        message,
        roundId: round.roundId,
        marketId: selectedMarket.marketId || selectedMarket.id,
        marketLabel: selectedMarket.label,
      }, embedConfig)
    } finally {
      setIsSubmittingBet(false)
    }
  }

  useEffect(() => {
    let active = true

    async function bootstrap() {
      try {
        const [currentRound, roundHistory] = await Promise.all([
          getCurrentRound(activeCameraId),
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

    const pollId = setInterval(() => {
      void loadCurrentRound()
    }, ROUND_POLL_INTERVAL_MS)

    const historyPollId = setInterval(() => {
      void loadHistory()
    }, 5000)

    startRoundConnection({
      onCountUpdated: (data) => {
        if (!active) return
        if (!isRoundForCamera(data, activeCameraId)) return
        updateRound(data)
      },
      onRoundUpdated: (data) => {
        if (!active) return
        if (!isRoundForCamera(data, activeCameraId)) return
        updateRound(data)
      },
      onRoundSettled: async (data) => {
        if (!active) return
        const isActiveCameraRound = isRoundForCamera(data, activeCameraId)
        const isPipelineRound = isRoundForPipeline(data, pipelineCameraIds)
        if (!isPipelineRound) return
        if (isActiveCameraRound) {
          reconcileRecentBets(data)
          setSelectedMarketId('')
          showToast('Round encerrado! Novo round iniciado.')
          await loadCurrentRound()
        }
        await loadHistory()
      },
      onRoundVoided: async (data) => {
        if (!active) return
        const isActiveCameraRound = isRoundForCamera(data, activeCameraId)
        const isPipelineRound = isRoundForPipeline(data, pipelineCameraIds)
        if (!isPipelineRound) return
        if (isActiveCameraRound) {
          reconcileRecentBets(data)
          setSelectedMarketId('')
          showToast('Round anulado. Carregando proximo round oficial.')
          await loadCurrentRound()
        }
        await loadHistory()
      },
    }).catch((err) => {
      if (!active) return
      console.error(err)
      setError('Falha ao conectar em tempo real.')
    })

    return () => {
      active = false
      clearInterval(pollId)
      clearInterval(historyPollId)
      stopRoundConnection().catch(console.error)
    }
  }, [activeCameraId, loadCurrentRound, loadHistory, pipelineCameraIds, reconcileRecentBets, updateRound])

  useEffect(() => {
    let active = true

    async function loadWorkerHealth() {
      try {
        const data = await getWorkerHealth()
        if (!active) return
        setWorkerHealth(data)
      } catch {
        if (!active) return
        setWorkerHealth((current) => current)
      }
    }

    void loadWorkerHealth()
    const intervalMs = isCameraTransitioning ? 500 : 2000
    const intervalId = setInterval(() => {
      void loadWorkerHealth()
    }, intervalMs)

    return () => {
      active = false
      clearInterval(intervalId)
    }
  }, [isCameraTransitioning])

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
    document.title = `${embedConfig.brand} | ${activeCameraLabel}`
    emitEmbedEvent('ready', {
      brand: embedConfig.brand,
      locale: embedConfig.locale,
      cameraId: activeCameraId,
      cameraLabel: activeCameraLabel,
      currency: embedConfig.currency,
      timezone: embedConfig.timezone,
      gameSessionId: embedConfig.gameSessionId,
      stakeOptions: embedConfig.stakeOptions,
      defaultStake: embedConfig.defaultStake,
      mode: embedConfig.mode,
    }, embedConfig)
  }, [activeCameraId, activeCameraLabel, embedConfig])

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
      cameraId: activeCameraId,
    }, embedConfig)
  }, [activeCameraId, displayCount, embedConfig, round])

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
        {/* Header */}
        <header className={`exchange-header${isTurboRound ? ' header-turbo' : ''}`}>
          <div className="header-left">
            <div className="header-brand-icon" aria-label="brand icon">🚗</div>
            <div className="header-title-block">
              <span className={`header-game-title${isTurboRound ? ' header-game-title-turbo' : ''}`}>{gameTitle}</span>
              {isTurboRound && <span className="turbo-badge">TURBO</span>}
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

        {/* Last results bar */}
        <div className="recents-bar">
          <LastResults history={recentHistory} overMarket={overMarket} />
        </div>

        {error && <div className="error-banner">{error}</div>}
        {toast && <div className="toast" key={toast.id}>{toast.message}</div>}

        {/* Main body */}
        <div className="exchange-body">
          <div className="left-panel">
            <div className="count-bar">
              <div className="count-bar-right">
                <span className="count-bar-label">TEMPO DO ROUND</span>
                <span className="count-bar-timer">
                  {padTime(timeLeftSeconds / 60)}:{padTime(timeLeftSeconds % 60)}
                </span>
              </div>
            </div>

            <div className="video-wrapper">
              <VideoPlayer
                webrtcSrc={webrtcSrc}
                src={hlsSrc}
                fallbackSrc={mjpegSrc}
                title={activeCameraLabel || 'Transmissão ao vivo'}
                transitionLabel={transitionCameraLabel || 'Nova câmera'}
                transitioning={isCameraTransitioning}
                countValue={displayCount}
              />
            </div>

              <HistoryDropdown
                history={filteredHistory}
                locale={embedConfig.locale}
                timezone={embedConfig.timezone}
              />
          </div>

          <div className="right-panel">
            <BettingPanel
              markets={markets}
              roundPhase={roundPhase}
              betCloseSeconds={betCloseSeconds}
              selectedMarketId={selectedMarketId}
              onMarketSelect={handleMarketSelect}
              onSubmitBet={handleSubmitBet}
              stakeAmount={stakeAmount}
              onStakeChange={setStakeAmount}
              stakeOptions={embedConfig.stakeOptions}
              locale={embedConfig.locale}
              currency={embedConfig.currency}
              balance={0}
              isSuspended={round?.isSuspended}
              recentBets={recentBets}
              isSubmittingBet={isSubmittingBet}
            />
            <DetectionsList detections={[]} />
          </div>
        </div>

        {/* Bottom market bar */}
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
