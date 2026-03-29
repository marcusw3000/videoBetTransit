import { useEffect, useMemo, useState } from 'react'
import CounterCard from './components/CounterCard'
import TimerCard from './components/TimerCard'
import HistoryCard from './components/HistoryCard'
import MarketCard from './components/MarketCard'
import VideoPlayer from './components/VideoPlayer'
import { getCurrentRound, getRoundHistory } from './services/roundApi'
import { startRoundConnection, stopRoundConnection } from './services/roundSignalr'
import { getRoundPhase, getTimeLeftInSeconds } from './utils/time'
import { WEBRTC_URL, HLS_URL, MJPEG_URL } from './config'
import { applyEmbedTheme, EMBED_CONFIG_EVENT, emitEmbedEvent, getEmbedConfig } from './embed'

const MAX_HISTORY_POINTS = 30
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

function MarketPage() {
  const [embedConfig, setEmbedConfig] = useState(() => getEmbedConfig())
  const [round, setRound] = useState(null)
  const [history, setHistory] = useState([])
  const [timeLeftSeconds, setTimeLeftSeconds] = useState(0)
  const [error, setError] = useState('')
  const [countHistory, setCountHistory] = useState([])
  const [toast, setToast] = useState(null)
  const [selectedMarketId, setSelectedMarketId] = useState('')
  const [stakeAmount, setStakeAmount] = useState(() => String(getEmbedConfig().defaultStake))

  const liveWebRtcUrl = WEBRTC_URL
  const liveStreamUrl = HLS_URL
  const liveFallbackUrl = MJPEG_URL
  const roundPhase = getRoundPhase(round)
  const betCloseSeconds = getTimeLeftInSeconds(round?.betCloseAt)
  const roundDurationLabel = getRoundDurationLabel(round)
  const markets = round?.markets || []
  const videoTitle = embedConfig.cameraLabel || 'Transmissao ao vivo'
  const numericStakeAmount = Number.parseFloat(String(stakeAmount).replace(',', '.'))
  const hasValidStake = Number.isFinite(numericStakeAmount) && numericStakeAmount > 0

  function showToast(message) {
    const id = Date.now()
    setToast({ message, id })
    setTimeout(() => setToast((t) => (t?.id === id ? null : t)), 4000)
  }

  async function loadCurrentRound() {
    try {
      const data = await getCurrentRound()
      setRound(data)
      setError('')
    } catch (err) {
      console.error(err)
      setError('Falha ao carregar o round atual.')
    }
  }

  async function loadHistory() {
    try {
      const data = await getRoundHistory()
      setHistory(data)
    } catch (err) {
      console.error(err)
    }
  }

  function handleMarketSelect(market) {
    if (!round) return
    if (!hasValidStake) {
      showToast('Escolha um valor de aposta valido antes de selecionar o mercado.')
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
    loadCurrentRound()
    loadHistory()

    startRoundConnection({
      onCountUpdated: (data) => {
        setRound(data)
        setCountHistory((prev) => {
          const next = [...prev, data.currentCount]
          return next.length > MAX_HISTORY_POINTS ? next.slice(-MAX_HISTORY_POINTS) : next
        })
      },
      onRoundSettled: async () => {
        setSelectedMarketId('')
        showToast('Round encerrado! Novo round iniciado.')
        setCountHistory([])
        await loadCurrentRound()
        await loadHistory()
      },
    }).catch((err) => {
      console.error(err)
      setError('Falha ao conectar em tempo real.')
    })

    return () => {
      stopRoundConnection().catch(console.error)
    }
  }, [])

  useEffect(() => {
    const handleConfigUpdate = () => {
      setEmbedConfig(getEmbedConfig())
    }

    window.addEventListener(EMBED_CONFIG_EVENT, handleConfigUpdate)
    return () => window.removeEventListener(EMBED_CONFIG_EVENT, handleConfigUpdate)
  }, [])

  useEffect(() => {
    applyEmbedTheme(embedConfig)
    document.title = `${embedConfig.brand} | ${embedConfig.cameraLabel}`
    setStakeAmount(String(embedConfig.defaultStake))
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
    setSelectedMarketId('')
  }, [round?.roundId])

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

  const recentHistory = useMemo(
    () => history.slice(0, RECENT_HISTORY_LIMIT),
    [history],
  )

  return (
    <div className="page">
      <div className="container">
        <header className="hero">
          <div>
            <h1>{embedConfig.brand}</h1>
            <p className="hero-kicker">
              {roundDurationLabel
                ? `${getDisplayName(round).toUpperCase()} · ${roundDurationLabel}`
                : getDisplayName(round).toUpperCase()}
            </p>
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
              webrtcSrc={liveWebRtcUrl}
              src={liveStreamUrl}
              fallbackSrc={liveFallbackUrl}
              title={videoTitle}
              resetKey={round?.roundId}
            />
          </div>

          <div className="stats-column">
            <CounterCard value={round?.currentCount} history={countHistory} />
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
              <span className="stake-helper">O valor escolhido segue junto para o betslip.</span>
            </div>

            <div className="stake-options" role="group" aria-label="Valores rapidos">
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
          <div className="markets-grid">
            {markets.length === 0 && (
              <div className="empty-state">Mercados indisponiveis para esta rodada.</div>
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
          <h2>Ultimos Resultados</h2>
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
