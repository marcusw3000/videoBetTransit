import { useEffect, useMemo, useState } from 'react'
import CounterCard from './components/CounterCard'
import TimerCard from './components/TimerCard'
import HistoryCard from './components/HistoryCard'
import MarketCard from './components/MarketCard'
import VideoPlayer from './components/VideoPlayer'
import { getCurrentRound, getRoundHistory, settleRound } from './services/roundApi'
import { startRoundConnection, stopRoundConnection } from './services/roundSignalr'
import { getRoundPhase, getTimeLeftInSeconds } from './utils/time'
import { WEBRTC_URL, HLS_URL, MJPEG_URL } from './config'

const MAX_HISTORY_POINTS = 30
const RECENT_HISTORY_LIMIT = 6

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
  const [round, setRound] = useState(null)
  const [history, setHistory] = useState([])
  const [timeLeftSeconds, setTimeLeftSeconds] = useState(0)
  const [isSettling, setIsSettling] = useState(false)
  const [error, setError] = useState('')
  const [countHistory, setCountHistory] = useState([])
  const [toast, setToast] = useState(null)

  const liveWebRtcUrl = WEBRTC_URL
  const liveStreamUrl = HLS_URL
  const liveFallbackUrl = MJPEG_URL
  const roundPhase = getRoundPhase(round)
  const betCloseSeconds = getTimeLeftInSeconds(round?.betCloseAt)
  const roundDurationLabel = getRoundDurationLabel(round)
  const markets = round?.ranges || []

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

  async function handleSettle() {
    try {
      setIsSettling(true)
      await settleRound()
      showToast('Round encerrado! Novo round iniciado.')
      setCountHistory([])
      await loadCurrentRound()
      await loadHistory()
    } catch (err) {
      console.error(err)
      setError('Falha ao encerrar o round.')
    } finally {
      setIsSettling(false)
    }
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
    const intervalId = setInterval(() => {
      if (round?.endsAt) {
        setTimeLeftSeconds(getTimeLeftInSeconds(round.endsAt))
      } else {
        setTimeLeftSeconds(0)
      }
    }, 1000)

    return () => clearInterval(intervalId)
  }, [round])

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
            <h1>Rodovia Market</h1>
            <p className="hero-kicker">
              {roundDurationLabel
                ? `${getDisplayName(round).toUpperCase()} · ${roundDurationLabel}`
                : getDisplayName(round).toUpperCase()}
            </p>
            <div className={statusClass}>Status: {getRoundPhaseLabel(roundPhase)}</div>
          </div>

          <div className="hero-actions">
            <button className="primary-button" onClick={handleSettle} disabled={isSettling}>
              {isSettling ? 'Encerrando...' : 'Encerrar / Novo Round'}
            </button>
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
              title="Rodovia Norte - Faixa A"
              resetKey={round?.id}
            />
          </div>

          <div className="stats-column">
            <CounterCard value={round?.currentCount} history={countHistory} />
            <TimerCard
              seconds={roundPhase === 'open' ? betCloseSeconds : timeLeftSeconds}
              label={roundPhase === 'open' ? 'Apostas Abertas Ate' : roundPhase === 'closing' ? 'Rodada em Fechamento' : 'Tempo Restante'}
              tone={roundPhase === 'closing' || roundPhase === 'settling' ? 'warning' : 'default'}
            />
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
                key={market.id}
                market={market}
                isActive={roundPhase === 'open'}
                roundStatus={roundPhase}
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
