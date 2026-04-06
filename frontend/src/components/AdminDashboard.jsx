import { useCallback, useEffect, useMemo, useState } from 'react'
import CounterCard from './CounterCard'
import CreateSessionPanel from './CreateSessionPanel'
import EventsFeed from './EventsFeed'
import HistoryCard from './HistoryCard'
import MetricsPanel from './MetricsPanel'
import OperationsCard from './OperationsCard'
import SessionStatus from './SessionStatus'
import TimerCard from './TimerCard'
import VideoPlayer from './VideoPlayer'
import { getEmbedConfig } from '../embed'
import { HLS_URL, MJPEG_URL, WEBRTC_URL } from '../config'
import { voidRound } from '../services/adminApi'
import { startMetricsConnection, stopMetricsConnection } from '../services/metricsSignalr'
import { getOperationsHealth } from '../services/operationsApi'
import { getCurrentRound, getRoundHistory } from '../services/roundApi'
import { getEvents, getMetrics, getSession, listSessions, stopSession } from '../services/streamApi'
import { getRoundPhase, getTimeLeftInSeconds } from '../utils/time'

function fmtDate(value) {
  if (!value) return '--'
  try {
    return new Date(value).toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return value
  }
}

function getActiveSession(sessions, sessionId) {
  if (!Array.isArray(sessions) || sessions.length === 0) return null
  return sessions.find((item) => item.id === sessionId)
    || sessions.find((item) => ['Running', 'Degraded', 'Starting', 'Ready', 'Created'].includes(item.status))
    || sessions[0]
}

export default function AdminDashboard() {
  const embedConfig = useMemo(() => getEmbedConfig(), [])
  const [sessions, setSessions] = useState([])
  const [selectedSessionId, setSelectedSessionId] = useState(() => sessionStorage.getItem('sessionId') || '')
  const [session, setSession] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [events, setEvents] = useState([])
  const [operations, setOperations] = useState(null)
  const [round, setRound] = useState(null)
  const [history, setHistory] = useState([])
  const [timerSeconds, setTimerSeconds] = useState(0)
  const [error, setError] = useState('')
  const [isStopping, setIsStopping] = useState(false)
  const [isVoiding, setIsVoiding] = useState(false)

  const activeSession = getActiveSession(sessions, selectedSessionId)
  const roundPhase = getRoundPhase(round)
  const streamState = operations?.streamConnected ? 'online' : 'connecting'
  const roundTimerLabel = roundPhase === 'open' ? 'Fechamento das Apostas' : 'Tempo Restante da Rodada'

  const loadSessions = useCallback(async () => {
    const { data } = await listSessions(false)
    setSessions(data)

    const nextSession = getActiveSession(data, selectedSessionId)
    if (nextSession && nextSession.id !== selectedSessionId) {
      setSelectedSessionId(nextSession.id)
      sessionStorage.setItem('sessionId', nextSession.id)
    }
  }, [selectedSessionId])

  const loadSessionDetails = useCallback(async (sessionId) => {
    if (!sessionId) {
      setSession(null)
      setMetrics(null)
      setEvents([])
      return
    }

    const [{ data: nextSession }, { data: nextMetrics }, { data: nextEvents }] = await Promise.all([
      getSession(sessionId),
      getMetrics(sessionId),
      getEvents(sessionId, 12),
    ])

    setSession(nextSession)
    setMetrics(nextMetrics)
    setEvents(Array.isArray(nextEvents) ? nextEvents : [])
  }, [])

  const loadOperations = useCallback(async () => {
    const data = await getOperationsHealth()
    setOperations(data)
  }, [])

  const loadRounds = useCallback(async () => {
    const [currentRound, roundHistory] = await Promise.all([
      getCurrentRound(embedConfig.cameraId),
      getRoundHistory(embedConfig.cameraId),
    ])
    setRound(currentRound)
    setHistory(Array.isArray(roundHistory) ? roundHistory : [])
  }, [embedConfig.cameraId])

  useEffect(() => {
    let active = true

    async function bootstrap() {
      const results = await Promise.allSettled([
        loadSessions(),
        loadOperations(),
        loadRounds(),
      ])

      if (!active) return

      const failed = results
        .map((result, index) => ({ result, index }))
        .filter(({ result }) => result.status === 'rejected')

      if (failed.length === 0) {
        setError('')
        return
      }

      failed.forEach(({ result }) => console.error(result.reason))

      const backendFailed = failed.some(({ index }) => index === 0 || index === 2)
      const operationsFailed = failed.some(({ index }) => index === 1)

      if (backendFailed && operationsFailed) {
        setError('Backend e worker estao indisponiveis no momento.')
      } else if (backendFailed) {
        setError('Backend indisponivel. O painel operacional segue com dados do worker.')
      } else {
        setError('Worker indisponivel. Os controles administrativos seguem disponiveis.')
      }
    }

    void bootstrap()

    const intervalId = setInterval(() => {
      void loadOperations().catch(console.error)
      void loadRounds().catch(console.error)
      void loadSessions().catch(console.error)
    }, 5000)

    return () => {
      active = false
      clearInterval(intervalId)
    }
  }, [loadOperations, loadRounds, loadSessions])

  useEffect(() => {
    void loadSessionDetails(selectedSessionId).catch((err) => {
      console.error(err)
      setError('Falha ao carregar os detalhes da sessão.')
    })
  }, [loadSessionDetails, selectedSessionId])

  useEffect(() => {
    if (!selectedSessionId) return undefined
    let active = true

    startMetricsConnection({
      sessionId: selectedSessionId,
      onMetricsUpdated: (payload) => {
        if (!active) return
        setMetrics(payload)
      },
      onStatusChanged: (payload) => {
        if (!active) return
        setSession(payload)
      },
    }).catch((err) => {
      console.error(err)
      setError('Falha ao conectar o painel em tempo real.')
    })

    return () => {
      active = false
      stopMetricsConnection().catch(console.error)
    }
  }, [selectedSessionId])

  useEffect(() => {
    const intervalId = setInterval(() => {
      if (!round) {
        setTimerSeconds(0)
        return
      }

      const nextSeconds = roundPhase === 'open'
        ? getTimeLeftInSeconds(round.betCloseAt)
        : getTimeLeftInSeconds(round.endsAt)

      setTimerSeconds(nextSeconds)
    }, 1000)

    return () => clearInterval(intervalId)
  }, [round, roundPhase])

  async function handleSessionCreated(sessionId) {
    sessionStorage.setItem('sessionId', sessionId)
    setSelectedSessionId(sessionId)
    await loadSessions()
    await loadSessionDetails(sessionId)
  }

  async function handleStopSession() {
    if (!session?.id) return
    setIsStopping(true)
    setError('')
    try {
      await stopSession(session.id)
      await loadSessions()
      await loadSessionDetails(session.id)
    } catch (err) {
      console.error(err)
      setError('Nao foi possivel parar a sessao selecionada.')
    } finally {
      setIsStopping(false)
    }
  }

  async function handleVoidRound() {
    if (!round?.roundId) return
    setIsVoiding(true)
    setError('')
    try {
      await voidRound(round.roundId)
      await loadRounds()
    } catch (err) {
      console.error(err)
      setError('Nao foi possivel anular o round atual.')
    } finally {
      setIsVoiding(false)
    }
  }

  return (
    <div className="admin-shell">
      <div className="admin-header">
        <div>
          <span className="admin-kicker">Painel Administrativo</span>
          <h1>Controle operacional do Traffic Counter</h1>
          <p>
            Administre sessoes, acompanhe saude do worker e monitore o round oficial da camera{' '}
            <strong>{embedConfig.cameraId}</strong>.
          </p>
        </div>

        <div className="admin-header-actions">
          <button type="button" className="admin-nav-btn" onClick={() => { window.location.href = '/' }}>
            Ir para Mercado
          </button>
          <button
            type="button"
            className="admin-danger-btn"
            onClick={handleVoidRound}
            disabled={!round?.roundId || isVoiding}
          >
            {isVoiding ? 'Anulando round...' : 'Anular Round Atual'}
          </button>
        </div>
      </div>

      {error && <div className="error-banner admin-error">{error}</div>}

      <div className="admin-layout">
        <section className="admin-main">
          <div className="card admin-video-card">
            <div className="admin-section-head">
              <div>
                <span className="label">Transmissao</span>
                <h2>Monitor ao vivo</h2>
              </div>
              <div className="admin-inline-stats">
                <span className="admin-inline-stat">
                  Round: <strong>{round?.currentCount ?? 0}</strong>
                </span>
                <span className="admin-inline-stat">
                  Worker: <strong>{operations?.totalCount ?? operations?.health?.totalCount ?? 0}</strong>
                </span>
              </div>
            </div>

            <div className="admin-video-wrapper">
              <VideoPlayer
                webrtcSrc={WEBRTC_URL}
                src={HLS_URL}
                fallbackSrc={MJPEG_URL}
                title={activeSession?.cameraName || embedConfig.cameraLabel || 'Camera ativa'}
                countValue={round?.currentCount ?? operations?.totalCount ?? operations?.health?.totalCount ?? 0}
              />
            </div>
          </div>

          <div className="admin-stats-grid">
            <CounterCard value={round?.currentCount ?? 0} />
            <TimerCard seconds={timerSeconds} label={roundTimerLabel} tone={roundPhase === 'closing' ? 'warning' : 'default'} />
            <MetricsPanel totalCount={metrics?.totalCount ?? session?.totalCount ?? 0} lastMinuteCount={metrics?.lastMinuteCount ?? 0} />
          </div>

          <OperationsCard
            operations={{ health: operations, updatedAt: Date.now() / 1000 }}
            streamState={streamState}
            lastEvent={{
              label: events[0]
                ? `${events[0].objectClass} #${events[0].trackId}`
                : null,
              at: events[0]?.timestampUtc,
            }}
          />

          <div className="admin-lower-grid">
            <EventsFeed events={events} />

            <div className="card admin-round-card">
              <div className="admin-section-head">
                <div>
                  <span className="label">Round Oficial</span>
                  <h3>{round?.displayName || 'Rodada Turbo'}</h3>
                </div>
                <span className={`admin-round-status admin-round-status-${roundPhase}`}>
                  {roundPhase.toUpperCase()}
                </span>
              </div>

              <div className="admin-round-meta">
                <div>
                  <span className="label">Criado em</span>
                  <strong>{fmtDate(round?.createdAt)}</strong>
                </div>
                <div>
                  <span className="label">Fecha apostas</span>
                  <strong>{fmtDate(round?.betCloseAt)}</strong>
                </div>
                <div>
                  <span className="label">Encerra em</span>
                  <strong>{fmtDate(round?.endsAt)}</strong>
                </div>
                <div>
                  <span className="label">Contagem</span>
                  <strong>{round?.currentCount ?? 0}</strong>
                </div>
              </div>

              <div className="admin-history-list">
                {history.slice(0, 4).map((item) => (
                  <HistoryCard
                    key={item.roundId || item.id}
                    item={item}
                    locale={embedConfig.locale}
                    timezone={embedConfig.timezone}
                  />
                ))}
              </div>
            </div>
          </div>
        </section>

        <aside className="admin-sidebar">
          <CreateSessionPanel
            onSessionCreated={handleSessionCreated}
            recentSessions={sessions.filter((item) => item.status !== 'Stopped').slice(0, 4)}
          />

          <div className="card admin-sessions-card">
            <div className="admin-section-head">
              <div>
                <span className="label">Sessoes</span>
                <h3>Pipelines cadastrados</h3>
              </div>
            </div>

            <div className="admin-session-list">
              {sessions.length === 0 && (
                <div className="admin-empty">Nenhuma sessao encontrada.</div>
              )}

              {sessions.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`admin-session-row${item.id === selectedSessionId ? ' is-active' : ''}`}
                  onClick={() => {
                    sessionStorage.setItem('sessionId', item.id)
                    setSelectedSessionId(item.id)
                  }}
                >
                  <div>
                    <strong>{item.cameraName || 'Camera sem nome'}</strong>
                    <span>{item.status}</span>
                  </div>
                  <span>{item.totalCount ?? 0}</span>
                </button>
              ))}
            </div>
          </div>

          <SessionStatus
            session={session || activeSession}
            onStop={handleStopSession}
            stopping={isStopping}
          />
        </aside>
      </div>
    </div>
  )
}
