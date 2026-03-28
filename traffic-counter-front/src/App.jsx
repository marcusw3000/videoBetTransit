import { useEffect, useMemo, useState } from 'react'
import CounterCard from './components/CounterCard'
import TimerCard from './components/TimerCard'
import HistoryCard from './components/HistoryCard'
import VideoPlayer from './components/VideoPlayer'
import { getCurrentRound, getRoundHistory, settleRound } from './services/roundApi'
import { startRoundConnection, stopRoundConnection } from './services/roundSignalr'
import { getTimeLeftInSeconds } from './utils/time'
import { MJPEG_URL } from './config'

const MAX_HISTORY_POINTS = 30
const RECENT_HISTORY_LIMIT = 6

function MarketPage() {
  const [round, setRound] = useState(null)
  const [history, setHistory] = useState([])
  const [timeLeftSeconds, setTimeLeftSeconds] = useState(0)
  const [isSettling, setIsSettling] = useState(false)
  const [error, setError] = useState('')
  const [countHistory, setCountHistory] = useState([])
  const [toast, setToast] = useState(null)

  const liveStreamUrl = MJPEG_URL

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
    const value = (round?.status || '').toLowerCase()

    if (value === 'running') return 'badge badge-live'
    if (value === 'settled') return 'badge badge-settled'
    return 'badge'
  }, [round])

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
            <div className={statusClass}>Status: {round?.status || 'loading'}</div>
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
              src={liveStreamUrl}
              title="Rodovia Norte - Faixa A"
              resetKey={round?.id}
            />
          </div>

          <div className="stats-column">
            <CounterCard value={round?.currentCount} history={countHistory} />
            <TimerCard seconds={timeLeftSeconds} />
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
