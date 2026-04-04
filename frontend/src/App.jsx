import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import TimerCard from './components/TimerCard'
import HistoryCard from './components/HistoryCard'
import MarketCard from './components/MarketCard'
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

function getRoundPhaseLabel(roundPhase) {
  switch (roundPhase) {
    case 'open':
      return 'Apostas Abertas'
    case 'closing':
      return 'Apostas Fechadas'
    case 'settling':
      return 'Apurando'
    case 'settled':
      return 'Encerrada'
    case 'void':
      return 'Anulada'
    default:
      return 'Carregando'
  }
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
  return `${minutes} ${minutes === 1 ? 'MINUTO' : 'MINUTOS'}`
}

function getHeroKicker(round, roundDurationLabel) {
  const displayName = getDisplayName(round).toUpperCase()
  return roundDurationLabel ? `${displayName} · ${roundDurationLabel}` : displayName
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

  const liveWebRtcUrl = WEBRTC_URL
  const liveStreamUrl = HLS_URL
  const liveFallbackUrl = MJPEG_URL
  const roundPhase = getRoundPhase(round)
  const betCloseSeconds = getTimeLeftInSeconds(round?.betCloseAt)
  const roundDurationLabel = getRoundDurationLabel(round)
  const markets = round?.markets || []
  const videoTitle = embedConfig.cameraLabel || 'Transmissão ao vivo'
  const numericStakeAmount = Number.parseFloat(String(stakeAmount).replace(',', '.'))
  const hasValidStake = Number.isFinite(numericStakeAmount) && numericStakeAmount > 0

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
    showToast(`${market.label || market.marketType} selecionado com ${formatCurrency(numericStakeAmount, embedConfig.locale, embedConfig.currency)}.`)
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

  const statusClass = useMemo(() => {
    if (roundPhase === 'open') return 'badge badge-live'
    if (roundPhase === 'closing') return 'badge badge-closing'
    if (roundPhase === 'settled') return 'badge badge-settled'
    return 'badge'
  }, [roundPhase])

  const recentHistory = useMemo(() => history.slice(0, RECENT_HISTORY_LIMIT), [history])

  return (
    <div className="page">
      <div className="container">
        <header className="hero">
          <div>
            <h1>{embedConfig.brand}</h1>
            <p className="hero-kicker">{getHeroKicker(round, roundDurationLabel)}</p>
            <div className={statusClass}>Status: {getRoundPhaseLabel(roundPhase)}</div>
          </div>

          <div className="hero-actions">
            <div className="hero-camera-pill">{embedConfig.cameraLabel}</div>
          </div>
        </header>

        {error && <div className="error-banner">{error}</div>}
        {toast && <div className="toast" key={toast.id}>{toast.message}</div>}

        <section className="top-grid">
          <div className="video-column">
            <VideoPlayer
              key={round?.roundId || 'live-player'}
              webrtcSrc={liveWebRtcUrl}
              src={liveStreamUrl}
              fallbackSrc={liveFallbackUrl}
              title={videoTitle}
              countValue={round?.currentCount}
            />
          </div>

          <div className="stats-column">
            <TimerCard
              seconds={roundPhase === 'open' ? betCloseSeconds : timeLeftSeconds}
              label={roundPhase === 'open' ? 'Janela de Aposta' : roundPhase === 'closing' ? 'Mercado Fechado' : 'Resultado Oficial em Breve'}
              tone={roundPhase === 'closing' || roundPhase === 'settling' ? 'warning' : 'default'}
            />
          </div>
        </section>

        <section className="stake-section">
          <div className="card stake-card">
            <div className="stake-header">
              <div>
                <span className="label">Valor da Aposta</span>
                <h2>{hasValidStake ? formatCurrency(numericStakeAmount, embedConfig.locale, embedConfig.currency) : 'Defina o valor'}</h2>
              </div>
              <span className="stake-helper">Selecione a stake antes de escolher o mercado.</span>
            </div>

            <div className="stake-options" role="group" aria-label="Valores rápidos">
              {embedConfig.stakeOptions.map((option) => (
                <button
                  key={option}
                  type="button"
                  className={`stake-chip${numericStakeAmount === option ? ' stake-chip-active' : ''}`}
                  onClick={() => setStakeAmount(String(option))}
                >
                  {formatCurrency(option, embedConfig.locale, embedConfig.currency)}
                </button>
              ))}
            </div>

            <label className="stake-input-group">
              <span>Outro valor</span>
              <input
                type="number"
                min="1"
                step="0.01"
                inputMode="decimal"
                className="stake-input"
                value={stakeAmount}
                onChange={(event) => setStakeAmount(event.target.value)}
                placeholder="0,00"
              />
            </label>
          </div>
        </section>

        <section className="markets-section">
          <h2>Mercados da Rodada</h2>
          <p className="section-subtitle">Escolha uma linha e envie a seleção para o betslip.</p>
          <div className="markets-grid">
            {markets.length === 0 && (
              <div className="empty-state">Mercados indisponíveis para esta rodada.</div>
            )}

            {markets.map((market) => (
              <MarketCard
                key={market.marketId || market.id}
                market={market}
                isActive={roundPhase === 'open' && !round?.isSuspended}
                roundStatus={roundPhase}
                onSelect={handleMarketSelect}
                isSelected={selectedMarketId === (market.marketId || market.id)}
                locale={embedConfig.locale}
                isSuspended={round?.isSuspended}
                requiresStake={!hasValidStake}
              />
            ))}
          </div>
        </section>

        <section className="history-section">
          <h2>Últimos Resultados</h2>
          <div className="history-list">
            {recentHistory.length === 0 && (
              <div className="empty-state">Nenhum round encerrado ainda.</div>
            )}

            {recentHistory.map((item) => (
              <HistoryCard
                key={item.id}
                item={item}
                locale={embedConfig.locale}
                timezone={embedConfig.timezone}
              />
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}

export default function App() {
  return <MarketPage />
}
