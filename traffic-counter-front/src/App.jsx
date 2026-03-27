import { useEffect, useMemo, useState } from 'react'
import CounterCard from './components/CounterCard'
import TimerCard from './components/TimerCard'
import RangeCard from './components/RangeCard'
import HistoryCard from './components/HistoryCard'
import VideoPlayer from './components/VideoPlayer'
import DetectionsList from './components/DetectionsList'
import CameraConfigPage from './pages/CameraConfigPage'
import { getCurrentRound, getRoundHistory, settleRound } from './services/roundApi'
import { startRoundConnection, stopRoundConnection } from './services/roundSignalr'
import { startOverlayConnection, stopOverlayConnection } from './services/overlaySignalr'
import { getTimeLeftInSeconds } from './utils/time'

const MAX_HISTORY_POINTS = 30

function MarketPage() {
  const [round, setRound] = useState(null)
  const [history, setHistory] = useState([])
  const [timeLeftSeconds, setTimeLeftSeconds] = useState(0)
  const [isSettling, setIsSettling] = useState(false)
  const [error, setError] = useState('')
  const [detectionFrame, setDetectionFrame] = useState(null)
  const [countHistory, setCountHistory] = useState([])
  const [toast, setToast] = useState(null)

  const liveStreamUrl = 'https://34.104.32.249.nip.io/SP125-KM093B/stream.m3u8'

  function showToast(message) {
    const id = Date.now()
    setToast({ message, id })
    setTimeout(() => setToast(t => t?.id === id ? null : t), 4000)
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

    // Round SignalR
    startRoundConnection({
      onCountUpdated: (data) => {
        setRound(data)
        setCountHistory(prev => {
          const next = [...prev, data.currentCount]
          return next.length > MAX_HISTORY_POINTS ? next.slice(-MAX_HISTORY_POINTS) : next
        })
      },
      onRoundSettled: async () => {
        showToast('Round encerrado! Novo round iniciado.')
        setCountHistory([])
        await loadCurrentRound()
        await loadHistory()
      }
    }).catch((err) => {
      console.error(err)
      setError('Falha ao conectar em tempo real.')
    })

    // Overlay SignalR
    startOverlayConnection({
      onLiveDetections: (data) => {
        setDetectionFrame(data)
      }
    }).catch((err) => {
      console.error('[Overlay]', err)
    })

    return () => {
      stopRoundConnection().catch(console.error)
      stopOverlayConnection().catch(console.error)
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

  return (
    <div className="page">
      <div className="container">
        <header className="hero">
          <div>
            <h1>Rodovia Market</h1>
            <div className={statusClass}>Status: {round?.status || 'loading'}</div>
          </div>

          <div className="hero-actions">
            <a href="#/admin/config" className="secondary-button">⚙️ Configurar</a>
            <button className="primary-button" onClick={handleSettle} disabled={isSettling}>
              {isSettling ? 'Encerrando...' : 'Encerrar / Novo Round'}
            </button>
          </div>
        </header>

        {error && <div className="error-banner">{error}</div>}
        {toast && (
          <div className="toast" key={toast.id}>{toast.message}</div>
        )}

        <section className="top-grid">
          <div className="video-column">
            <VideoPlayer
              src={liveStreamUrl}
              title="Rodovia Norte - Faixa A"
              detectionFrame={detectionFrame}
            />
          </div>

          <div className="stats-column">
            <CounterCard value={round?.currentCount} history={countHistory} />
            <TimerCard seconds={timeLeftSeconds} />
          </div>
        </section>

        {/* Lista de detecções */}
        <section style={{ marginBottom: 28 }}>
          <DetectionsList detections={detectionFrame?.detections || []} />
        </section>

        <section className="ranges-section">
          <h2>Faixas</h2>
          <div className="ranges-grid">
            {(round?.ranges || []).map((range) => (
              <RangeCard
                key={range.id}
                range={range}
                isActive={
                  round?.currentCount !== undefined &&
                  round.currentCount >= range.min &&
                  round.currentCount <= range.max
                }
              />
            ))}
          </div>
        </section>

        <section className="history-section">
          <h2>Histórico</h2>
          <div className="history-list">
            {history.length === 0 && <div className="empty-state">Nenhum round finalizado ainda.</div>}

            {history.map((item) => (
              <HistoryCard key={item.id} item={item} />
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}

// Simple hash-based router
export default function App() {
  const [page, setPage] = useState(window.location.hash)

  useEffect(() => {
    const onHashChange = () => setPage(window.location.hash)
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  if (page === '#/admin/config') {
    return <CameraConfigPage />
  }

  return <MarketPage />
}
