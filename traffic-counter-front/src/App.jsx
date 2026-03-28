import { useEffect, useMemo, useState } from 'react'
import CounterCard from './components/CounterCard'
import TimerCard from './components/TimerCard'
import RangeCard from './components/RangeCard'
import HistoryCard from './components/HistoryCard'
import VideoPlayer from './components/VideoPlayer'
import DetectionsList from './components/DetectionsList'
import OperationsCard from './components/OperationsCard'
import AlertsPanel from './components/AlertsPanel'
import { getCurrentRound, getRoundCountEvents, getRoundHistory, settleRound } from './services/roundApi'
import { startRoundConnection, stopRoundConnection } from './services/roundSignalr'
import { startOverlayConnection, stopOverlayConnection } from './services/overlaySignalr'
import { getOperationsHealth } from './services/operationsApi'
import { getTimeLeftInSeconds } from './utils/time'
import { MJPEG_URL } from './config'

const MAX_HISTORY_POINTS = 30
const STALE_FRAME_THRESHOLD_SECONDS = 10
const ZERO_COUNT_ALERT_SECONDS = 120

function secondsSince(value) {
  if (!value) return null

  const parsed = Number.isFinite(value) ? value * 1000 : Date.parse(value)
  if (Number.isNaN(parsed)) return null

  return Math.max(0, Math.floor((Date.now() - parsed) / 1000))
}

function isWithinPeriod(isoDate, period) {
  if (!isoDate || period === 'all') return true

  const value = new Date(isoDate).getTime()
  if (Number.isNaN(value)) return false

  const now = Date.now()
  if (period === 'today') {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    return value >= today.getTime()
  }

  const periodDays = { '7d': 7, '30d': 30 }
  const days = periodDays[period]
  if (!days) return true
  return value >= now - days * 24 * 60 * 60 * 1000
}

function escapeCsv(value) {
  const normalized = value == null ? '' : String(value)
  return `"${normalized.replaceAll('"', '""')}"`
}

function buildRoundsCsv(rounds, summaries) {
  const header = ['round_id', 'status', 'created_at', 'ends_at', 'final_count', 'camera_ids', 'events_count']
  const rows = rounds.map((round) => {
    const summary = summaries[round.id] || { cameraIds: [], eventsCount: 0 }
    return [
      round.id,
      round.status,
      round.createdAt,
      round.endsAt,
      round.finalCount ?? '',
      summary.cameraIds.join('|'),
      summary.eventsCount,
    ].map(escapeCsv).join(',')
  })
  return [header.join(','), ...rows].join('\n')
}

function buildEventsCsv(rounds, eventsByRound) {
  const header = ['round_id', 'camera_id', 'track_id', 'vehicle_type', 'crossed_at', 'total_count', 'snapshot_url']
  const rows = rounds.flatMap((round) => (
    (eventsByRound[round.id] || []).map((event) => (
      [
        round.id,
        event.cameraId,
        event.trackId,
        event.vehicleType,
        event.crossedAt,
        event.totalCount,
        event.snapshotUrl,
      ].map(escapeCsv).join(',')
    ))
  ))
  return [header.join(','), ...rows].join('\n')
}

function downloadCsv(filename, content) {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

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
  const [historyEventsByRound, setHistoryEventsByRound] = useState({})
  const [historySummaryByRound, setHistorySummaryByRound] = useState({})
  const [historyCameraFilter, setHistoryCameraFilter] = useState('all')
  const [historyPeriodFilter, setHistoryPeriodFilter] = useState('all')
  const [historyRoundQuery, setHistoryRoundQuery] = useState('')

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
      const eventsEntries = await Promise.all(
        data.map(async (round) => {
          try {
            const events = await getRoundCountEvents(round.id)
            return [round.id, events]
          } catch (err) {
            console.error(`[History] Falha ao carregar eventos do round ${round.id}`, err)
            return [round.id, []]
          }
        }),
      )

      const nextEventsByRound = Object.fromEntries(eventsEntries)
      const nextSummaryByRound = Object.fromEntries(
        eventsEntries.map(([roundId, events]) => {
          const cameraIds = [...new Set(events.map((event) => event.cameraId).filter(Boolean))]
          return [roundId, { cameraIds, eventsCount: events.length }]
        }),
      )

      setHistoryEventsByRound(nextEventsByRound)
      setHistorySummaryByRound(nextSummaryByRound)
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

  const alerts = useMemo(() => {
    const next = []
    const health = operations?.health
    const backend = health?.backend ?? {}
    const lastFrameAgeSeconds = secondsSince(health?.lastFrameAt)
    const lastCountSignalAgeSeconds = secondsSince(lastEvent?.at)

    if (streamState === 'error') {
      next.push({
        id: 'stream-down',
        severity: 'error',
        badge: 'Feed',
        title: 'Stream anotado indisponivel',
        message: 'O navegador nao conseguiu carregar o MJPEG anotado.',
        at: operations?.updatedAt,
      })
    }

    if (operations?.backendError || backend?.lastError) {
      next.push({
        id: 'backend-offline',
        severity: 'error',
        badge: 'Backend',
        title: 'Backend com falha recente',
        message: operations?.backendError || backend?.lastError || 'A integracao com o backend apresentou falha.',
        at: backend?.lastErrorAt || operations?.updatedAt,
      })
    }

    if (lastFrameAgeSeconds !== null && lastFrameAgeSeconds > STALE_FRAME_THRESHOLD_SECONDS) {
      next.push({
        id: 'frames-stale',
        severity: 'warn',
        badge: 'Frames',
        title: 'Feed sem frames recentes',
        message: `A engine nao reporta frames novos ha ${lastFrameAgeSeconds}s.`,
        at: health?.lastFrameAt,
      })
    }

    if (
      health?.streamConnected &&
      Number(health?.totalCount ?? 0) === 0 &&
      lastCountSignalAgeSeconds !== null &&
      lastCountSignalAgeSeconds > ZERO_COUNT_ALERT_SECONDS
    ) {
      next.push({
        id: 'zero-count',
        severity: 'warn',
        badge: 'Contagem',
        title: 'Contagem zerada por tempo suspeito',
        message: `Nenhum evento relevante chegou ha ${lastCountSignalAgeSeconds}s, apesar do stream estar ativo.`,
        at: lastEvent?.at,
      })
    }

    return next
  }, [lastEvent, operations, streamState])

  const availableHistoryCameras = useMemo(() => {
    const cameras = Object.values(historySummaryByRound)
      .flatMap((summary) => summary.cameraIds || [])
      .filter(Boolean)

    return [...new Set(cameras)].sort()
  }, [historySummaryByRound])

  const filteredHistory = useMemo(() => {
    const normalizedQuery = historyRoundQuery.trim().toLowerCase()

    return history.filter((item) => {
      const summary = historySummaryByRound[item.id] || { cameraIds: [] }
      const matchesCamera = historyCameraFilter === 'all' || summary.cameraIds.includes(historyCameraFilter)
      const matchesPeriod = isWithinPeriod(item.endsAt || item.createdAt, historyPeriodFilter)
      const matchesRound = !normalizedQuery || item.id.toLowerCase().includes(normalizedQuery)
      return matchesCamera && matchesPeriod && matchesRound
    })
  }, [history, historyCameraFilter, historyPeriodFilter, historyRoundQuery, historySummaryByRound])

  const historyTrend = useMemo(() => {
    const points = filteredHistory.map((item) => item.finalCount ?? 0).reverse()

    if (!points.length) {
      return { average: 0, peak: 0, totalEvents: 0, points: '' }
    }

    const average = points.reduce((sum, value) => sum + value, 0) / points.length
    const peak = Math.max(...points)
    const totalEvents = filteredHistory.reduce((sum, item) => sum + (historySummaryByRound[item.id]?.eventsCount ?? 0), 0)
    const width = 260
    const height = 56
    const max = Math.max(...points, 1)
    const polyline = points.map((value, index) => {
      const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width
      const y = height - (value / max) * (height - 8) - 4
      return `${x.toFixed(1)},${y.toFixed(1)}`
    }).join(' ')

    return { average, peak, totalEvents, points: polyline }
  }, [filteredHistory, historySummaryByRound])

  function handleExportHistory() {
    const stamp = new Date().toISOString().slice(0, 19).replaceAll(':', '-')
    downloadCsv(`rounds-${stamp}.csv`, buildRoundsCsv(filteredHistory, historySummaryByRound))
    downloadCsv(`count-events-${stamp}.csv`, buildEventsCsv(filteredHistory, historyEventsByRound))
  }

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

        <section className="alerts-section">
          <AlertsPanel alerts={alerts} />
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
          <div className="history-toolbar">
            <input
              className="history-input"
              placeholder="Buscar por ID do round"
              value={historyRoundQuery}
              onChange={(event) => setHistoryRoundQuery(event.target.value)}
            />
            <select
              className="history-select"
              value={historyCameraFilter}
              onChange={(event) => setHistoryCameraFilter(event.target.value)}
            >
              <option value="all">Todas as cameras</option>
              {availableHistoryCameras.map((cameraId) => (
                <option key={cameraId} value={cameraId}>{cameraId}</option>
              ))}
            </select>
            <select
              className="history-select"
              value={historyPeriodFilter}
              onChange={(event) => setHistoryPeriodFilter(event.target.value)}
            >
              <option value="all">Todo periodo</option>
              <option value="today">Hoje</option>
              <option value="7d">Ultimos 7 dias</option>
              <option value="30d">Ultimos 30 dias</option>
            </select>
            <button className="secondary-button" onClick={handleExportHistory}>
              Exportar CSV
            </button>
          </div>

          <div className="history-summary">
            <div className="card history-summary-card">
              <span className="label">Tendencia</span>
              <div className="history-summary-metrics">
                <div>
                  <span className="history-summary-label">Rounds filtrados</span>
                  <strong>{filteredHistory.length}</strong>
                </div>
                <div>
                  <span className="history-summary-label">Media final</span>
                  <strong>{historyTrend.average.toFixed(1)}</strong>
                </div>
                <div>
                  <span className="history-summary-label">Pico</span>
                  <strong>{historyTrend.peak}</strong>
                </div>
                <div>
                  <span className="history-summary-label">Eventos</span>
                  <strong>{historyTrend.totalEvents}</strong>
                </div>
              </div>
              {historyTrend.points ? (
                <svg viewBox="0 0 260 56" className="history-trend" aria-hidden="true">
                  <polyline
                    points={historyTrend.points}
                    fill="none"
                    stroke="rgba(128, 216, 160, 0.95)"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              ) : (
                <div className="empty-state">Sem dados suficientes para tendencia.</div>
              )}
            </div>
          </div>

          <div className="history-list">
            {filteredHistory.length === 0 && <div className="empty-state">Nenhum round encontrado com os filtros atuais.</div>}

            {filteredHistory.map((item) => (
              <HistoryCard
                key={item.id}
                item={item}
                summary={historySummaryByRound[item.id]}
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
