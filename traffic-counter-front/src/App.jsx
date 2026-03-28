import { useEffect, useMemo, useState } from 'react'
import CounterCard from './components/CounterCard'
import TimerCard from './components/TimerCard'
import RangeCard from './components/RangeCard'
import HistoryCard from './components/HistoryCard'
import VideoPlayer from './components/VideoPlayer'
import DetectionsList from './components/DetectionsList'
import OperationsCard from './components/OperationsCard'
import { getCurrentRound, getRoundHistory, settleRound } from './services/roundApi'
import { startRoundConnection, stopRoundConnection } from './services/roundSignalr'
import { startOverlayConnection, stopOverlayConnection } from './services/overlaySignalr'
import { getOperationsHealth } from './services/operationsApi'
import { getTimeLeftInSeconds } from './utils/time'
import { MJPEG_URL } from './config'

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
  const [operations, setOperations] = useState({ health: null, backendError: null, updatedAt: null })
  const [streamState, setStreamState] = useState('connecting')
  const [lastEvent, setLastEvent] = useState(null)

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
      setOperations((prev) => ({ ...prev, backendError: null }))
    } catch (err) {
      console.error(err)
      setError('Falha ao carregar o round atual.')
      setOperations((prev) => ({ ...prev, backendError: err?.message || 'Falha ao consultar backend.' }))
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
      setLastEvent({
        label: 'Round encerrado manualmente',
        at: new Date().toISOString(),
      })
      await loadCurrentRound()
      await loadHistory()
    } catch (err) {
      console.error(err)
      setError('Falha ao encerrar o round.')
    } finally {
      setIsSettling(false)
    }
  }

  async function loadOperationsHealth() {
    try {
      const health = await getOperationsHealth()
      setOperations({
        health,
        backendError: null,
        updatedAt: new Date().toISOString(),
      })
    } catch (err) {
      console.error('[Operations]', err)
      setOperations((prev) => ({
        health: prev.health,
        backendError: err?.message || 'Falha ao consultar health operacional.',
        updatedAt: new Date().toISOString(),
      }))
    }
  }

  useEffect(() => {
    loadCurrentRound()
    loadHistory()
    loadOperationsHealth()

    startRoundConnection({
      onCountUpdated: (data) => {
        setRound(data)
        setLastEvent({
          label: `Contagem atualizada para ${data.currentCount}`,
          at: new Date().toISOString(),
        })
        setCountHistory((prev) => {
          const next = [...prev, data.currentCount]
          return next.length > MAX_HISTORY_POINTS ? next.slice(-MAX_HISTORY_POINTS) : next
        })
      },
      onRoundSettled: async () => {
        showToast('Round encerrado! Novo round iniciado.')
        setLastEvent({
          label: 'Round encerrado automaticamente e reiniciado',
          at: new Date().toISOString(),
        })
        setCountHistory([])
        await loadCurrentRound()
        await loadHistory()
      },
    }).catch((err) => {
      console.error(err)
      setError('Falha ao conectar em tempo real.')
    })

    startOverlayConnection({
      onLiveDetections: (data) => {
        setDetectionFrame(data)
        setLastEvent({
          label: `${data?.detections?.length ?? 0} deteccoes ao vivo recebidas`,
          at: new Date().toISOString(),
        })
      },
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

  useEffect(() => {
    const intervalId = setInterval(() => {
      loadOperationsHealth()
    }, 5000)

    return () => clearInterval(intervalId)
  }, [])

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
            <button className="primary-button" onClick={handleSettle} disabled={isSettling}>
              {isSettling ? 'Encerrando...' : 'Encerrar / Novo Round'}
            </button>
          </div>
        </header>

        {error && <div className="error-banner">{error}</div>}
        {toast && <div className="toast" key={toast.id}>{toast.message}</div>}

        <section className="operations-section">
          <OperationsCard
            operations={operations}
            streamState={streamState}
            lastEvent={lastEvent}
          />
        </section>

        <section className="top-grid">
          <div className="video-column">
            <VideoPlayer
              src={liveStreamUrl}
              title="Rodovia Norte - Faixa A"
              onStreamStatusChange={setStreamState}
            />
          </div>

          <div className="stats-column">
            <CounterCard value={round?.currentCount} history={countHistory} />
            <TimerCard seconds={timeLeftSeconds} />
          </div>
        </section>

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
          <h2>Historico</h2>
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

export default function App() {
  return <MarketPage />
}
