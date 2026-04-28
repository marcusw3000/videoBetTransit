import { useCallback, useEffect, useMemo, useState } from 'react'
import CounterCard from './CounterCard'
import CrossingEventsCard from './CrossingEventsCard'
import CreateSessionPanel from './CreateSessionPanel'
import EventsFeed from './EventsFeed'
import HistoryCard from './HistoryCard'
import MetricsPanel from './MetricsPanel'
import OperationsCard from './OperationsCard'
import RoundSummaryCard from './RoundSummaryCard'
import RoundTimeline from './RoundTimeline'
import SessionStatus from './SessionStatus'
import TimerCard from './TimerCard'
import VideoPlayer from './VideoPlayer'
import { getEmbedConfig } from '../embed'
import { buildHlsUrlFromPath, buildMjpegUrl, buildWebRtcWrapperUrlFromPath } from '../config'
import { voidRound } from '../services/adminApi'
import { startMetricsConnection, stopMetricsConnection } from '../services/metricsSignalr'
import { getOperationsHealth } from '../services/operationsApi'
import {
  getCurrentRound,
  getRecentRounds,
  getRoundById,
  getRoundCountEvents,
  getRoundHistory,
  getRoundTimeline,
} from '../services/roundApi'
import { startRoundConnection, stopRoundConnection } from '../services/roundSignalr'
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

function mergeRounds(...groups) {
  const map = new Map()

  groups.flat().filter(Boolean).forEach((round) => {
    if (!round?.roundId) return
    if (!map.has(round.roundId)) {
      map.set(round.roundId, round)
    }
  })

  return Array.from(map.values()).sort((a, b) => {
    const left = new Date(b?.createdAt || 0).getTime()
    const right = new Date(a?.createdAt || 0).getTime()
    return left - right
  })
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

function getRuntimeHistoryCameraIds(operations, activeCameraId) {
  const activated = Array.isArray(operations?.recentRuntimeCameraIds || operations?.health?.recentRuntimeCameraIds)
    ? (operations?.recentRuntimeCameraIds || operations?.health?.recentRuntimeCameraIds)
        .map((item) => String(item || '').trim())
        .filter(Boolean)
    : []

  if (activated.length > 0) return activated

  const fallback = String(activeCameraId || '').trim()
  return fallback ? [fallback] : []
}

function isAwaitingFrontendAck(operations) {
  const phase = String(operations?.frontendAckPhase || operations?.health?.frontendAckPhase || '').trim().toLowerCase()
  const required = Boolean(operations?.frontendAckRequired ?? operations?.health?.frontendAckRequired)
  if (!required) return false
  return phase === 'requested' || phase === 'frontend_pending'
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

function getRoundStatusLabel(round) {
  const status = String(round?.status || 'desconhecido').toLowerCase()

  switch (status) {
    case 'open':
      return 'Aberto'
    case 'closing':
      return 'Fechado para apostas'
    case 'settling':
      return 'Em apuracao'
    case 'settled':
      return 'Liquidado'
    case 'void':
      return 'Anulado'
    default:
      return status || '--'
  }
}

function getRoundButtonLabel(round) {
  if (!round) return 'Round sem dados'
  return `${getRoundStatusLabel(round)} • count ${round.finalCount ?? round.currentCount ?? 0}`
}

function isVoidable(round) {
  const status = String(round?.status || '').toLowerCase()
  return Boolean(round?.roundId) && status !== 'settled' && status !== 'void'
}

export default function AdminDashboard() {
  const embedConfig = useMemo(() => getEmbedConfig(), [])
  const [sessions, setSessions] = useState([])
  const [selectedSessionId, setSelectedSessionId] = useState(() => sessionStorage.getItem('sessionId') || '')
  const [session, setSession] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [events, setEvents] = useState([])
  const [operations, setOperations] = useState(null)
  const [currentRound, setCurrentRound] = useState(null)
  const [inspectedRound, setInspectedRound] = useState(null)
  const [history, setHistory] = useState([])
  const [recentRounds, setRecentRounds] = useState([])
  const [roundEvents, setRoundEvents] = useState([])
  const [roundTimeline, setRoundTimeline] = useState([])
  const [selectedRoundId, setSelectedRoundId] = useState('')
  const [roundLookup, setRoundLookup] = useState('')
  const [timelineFilter, setTimelineFilter] = useState('all')
  const [timerSeconds, setTimerSeconds] = useState(0)
  const [error, setError] = useState('')
  const [isStopping, setIsStopping] = useState(false)
  const [isVoiding, setIsVoiding] = useState(false)
  const [isLoadingRoundDetail, setIsLoadingRoundDetail] = useState(false)
  const [frontendTransportState, setFrontendTransportState] = useState('connecting')

  const activeSession = getActiveSession(sessions, selectedSessionId)
  const roundPhase = getRoundPhase(currentRound)
  const streamState = frontendTransportState
  const roundTimerLabel = roundPhase === 'open' ? 'Fechamento das Apostas' : 'Tempo Restante da Rodada'
  const cameraActivation = operations?.cameraActivation || operations?.health?.cameraActivation || null
  const isCameraTransitioning = Boolean(cameraActivation && cameraActivation.phase !== 'ready')
  const activeStreamPath = cameraActivation?.readyProcessedStreamPath || operations?.processedStreamPath || operations?.health?.processedStreamPath || ''
  const activeCameraId = cameraActivation?.readyCameraId || operations?.cameraId || operations?.health?.cameraId || embedConfig.cameraId
  const transitionCameraLabel = cameraActivation?.requestedProfileLabel || cameraActivation?.requestedCameraId || activeCameraId
  const pipelineCameraIds = useMemo(
    () => getRuntimeHistoryCameraIds(operations, activeCameraId),
    [operations, activeCameraId],
  )
  const filteredHistory = useMemo(
    () => filterHistoryByPipelineCameras(history, pipelineCameraIds),
    [history, pipelineCameraIds],
  )
  const webrtcSrc = useMemo(
    () => buildWebRtcWrapperUrlFromPath(activeStreamPath, activeCameraId),
    [activeCameraId, activeStreamPath],
  )
  const hlsSrc = useMemo(
    () => buildHlsUrlFromPath(activeStreamPath, activeCameraId),
    [activeCameraId, activeStreamPath],
  )
  const mjpegSrc = useMemo(() => buildMjpegUrl(), [])

  const evidenceEvents = useMemo(
    () => roundEvents.filter((item) => Boolean(item?.snapshotUrl)).slice(0, 6),
    [roundEvents],
  )
  const selectedRoundMarkets = inspectedRound?.markets || []

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

  const loadRoundArtifacts = useCallback(async (roundId) => {
    if (!roundId) {
      setRoundEvents([])
      setRoundTimeline([])
      return
    }

    const [crossingEvents, timeline] = await Promise.all([
      getRoundCountEvents(roundId),
      getRoundTimeline(roundId),
    ])

    setRoundEvents(Array.isArray(crossingEvents) ? crossingEvents : [])
    setRoundTimeline(Array.isArray(timeline) ? timeline : [])
  }, [])

  const loadRoundDetail = useCallback(async (roundId, fallbackRound = null) => {
    if (!roundId) {
      setSelectedRoundId('')
      setRoundLookup('')
      setInspectedRound(null)
      await loadRoundArtifacts('')
      return
    }

    setIsLoadingRoundDetail(true)
    try {
      const round = fallbackRound && fallbackRound.roundId === roundId
        ? fallbackRound
        : await getRoundById(roundId)

      setSelectedRoundId(roundId)
      setRoundLookup(roundId)
      setInspectedRound(round)
      await loadRoundArtifacts(roundId)
    } finally {
      setIsLoadingRoundDetail(false)
    }
  }, [loadRoundArtifacts])

  const loadRounds = useCallback(async (preferredRoundId = '') => {
    const [currentRoundResult, roundHistory, nextRecentRounds] = await Promise.all([
      getCurrentRound(activeCameraId).then((value) => ({ ok: true, value })).catch((error) => ({ ok: false, error })),
      getRoundHistory(),
      getRecentRounds(activeCameraId, 12),
    ])

    if (!currentRoundResult.ok) {
      if (currentRoundResult.error?.response?.status !== 404 || !isAwaitingFrontendAck(operations)) {
        throw currentRoundResult.error
      }
    }

    const nextCurrentRound = currentRoundResult.ok ? currentRoundResult.value : null

    setCurrentRound(nextCurrentRound)
    setHistory(Array.isArray(roundHistory) ? roundHistory : [])

    const mergedRecentRounds = mergeRounds(nextCurrentRound, nextRecentRounds, roundHistory)
    setRecentRounds(mergedRecentRounds)

    const targetRoundId = preferredRoundId || selectedRoundId || nextCurrentRound?.roundId || ''
    const fallbackRound = mergedRecentRounds.find((item) => item.roundId === targetRoundId) || null
    await loadRoundDetail(targetRoundId, fallbackRound)
  }, [activeCameraId, loadRoundDetail, selectedRoundId])

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
      void loadRounds(selectedRoundId).catch(console.error)
      void loadSessions().catch(console.error)
    }, isCameraTransitioning ? 750 : 5000)

    return () => {
      active = false
      clearInterval(intervalId)
    }
  }, [isCameraTransitioning, loadOperations, loadRounds, loadSessions, selectedRoundId])

  useEffect(() => {
    void loadSessionDetails(selectedSessionId).catch((err) => {
      console.error(err)
      setError('Falha ao carregar os detalhes da sessao.')
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
    let active = true

    startRoundConnection({
      onCountUpdated: async (payload) => {
        if (!active) return
        if (payload?.cameraId !== activeCameraId) return
        setCurrentRound(payload)
        setRecentRounds((prev) => mergeRounds(payload, prev))
        if (!selectedRoundId || payload?.roundId === selectedRoundId) {
          setInspectedRound(payload)
          await loadRoundArtifacts(payload?.roundId)
        }
      },
      onRoundUpdated: async (payload) => {
        if (!active) return
        if (payload?.cameraId !== activeCameraId) return
        setCurrentRound(payload)
        setRecentRounds((prev) => mergeRounds(payload, prev))
        if (!selectedRoundId || payload?.roundId === selectedRoundId) {
          setInspectedRound(payload)
          await loadRoundArtifacts(payload?.roundId)
        }
      },
      onRoundSettled: async (payload) => {
        if (!active) return
        if (!isRoundForPipeline(payload, pipelineCameraIds)) return
        if (payload?.cameraId === activeCameraId) {
          setCurrentRound(payload)
        }
        await loadRounds(selectedRoundId || payload?.roundId)
      },
      onRoundVoided: async (payload) => {
        if (!active) return
        if (!isRoundForPipeline(payload, pipelineCameraIds)) return
        if (payload?.cameraId === activeCameraId) {
          setCurrentRound(payload)
        }
        await loadRounds(selectedRoundId || payload?.roundId)
      },
    }).catch((err) => {
      console.error(err)
    })

    return () => {
      active = false
      stopRoundConnection().catch(console.error)
    }
  }, [activeCameraId, loadRoundArtifacts, loadRounds, pipelineCameraIds, selectedRoundId])

  useEffect(() => {
    const intervalId = setInterval(() => {
      if (!currentRound) {
        setTimerSeconds(0)
        return
      }

      const nextSeconds = roundPhase === 'open'
        ? getTimeLeftInSeconds(currentRound.betCloseAt)
        : getTimeLeftInSeconds(currentRound.endsAt)

      setTimerSeconds(nextSeconds)
    }, 1000)

    return () => clearInterval(intervalId)
  }, [currentRound, roundPhase])

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
    if (!inspectedRound?.roundId) return
    setIsVoiding(true)
    setError('')
    try {
      await voidRound(inspectedRound.roundId)
      await loadRounds(inspectedRound.roundId)
    } catch (err) {
      console.error(err)
      setError('Nao foi possivel anular o round selecionado.')
    } finally {
      setIsVoiding(false)
    }
  }

  async function handleRoundLookupSubmit(event) {
    event.preventDefault()
    const roundId = roundLookup.trim()
    if (!roundId) return

    setError('')
    try {
      await loadRoundDetail(roundId)
    } catch (err) {
      console.error(err)
      setError('Nao foi possivel localizar o round informado.')
    }
  }

  async function handleRoundSelection(roundId) {
    if (!roundId) return
    setError('')
    try {
      const fallbackRound = recentRounds.find((item) => item.roundId === roundId) || null
      await loadRoundDetail(roundId, fallbackRound)
    } catch (err) {
      console.error(err)
      setError('Falha ao carregar o round selecionado.')
    }
  }

  return (
    <div className="admin-shell">
      <div className="admin-header">
        <div>
          <span className="admin-kicker">Painel Administrativo</span>
          <h1>Backoffice operacional do Traffic Counter</h1>
          <p>
            Investigue rounds oficiais, confira crossings persistidos e acompanhe a saude operacional da camera{' '}
            <strong>{activeCameraId}</strong>.
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
            disabled={!isVoidable(inspectedRound) || isVoiding}
          >
            {isVoiding ? 'Anulando round...' : 'Anular Round Selecionado'}
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
                  Round atual: <strong>{currentRound?.currentCount ?? 0}</strong>
                </span>
                <span className="admin-inline-stat">
                  Worker: <strong>{operations?.totalCount ?? operations?.health?.totalCount ?? 0}</strong>
                </span>
              </div>
            </div>

            <div className="admin-video-wrapper">
              <VideoPlayer
                webrtcSrc={webrtcSrc}
                src={hlsSrc}
                fallbackSrc={mjpegSrc}
                title={activeSession?.cameraName || embedConfig.cameraLabel || 'Camera ativa'}
                transitionLabel={transitionCameraLabel}
                transitioning={isCameraTransitioning}
                countValue={currentRound?.currentCount ?? operations?.totalCount ?? operations?.health?.totalCount ?? 0}
                onStreamStatusChange={setFrontendTransportState}
              />
            </div>
          </div>

          <div className="admin-stats-grid">
            <CounterCard value={currentRound?.currentCount ?? 0} />
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
                  <span className="label">Backoffice de rounds</span>
                  <h3>Investigacao oficial da camera</h3>
                </div>
                <button
                  type="button"
                  className="load-btn"
                  onClick={() => { void loadRounds(selectedRoundId) }}
                >
                  Recarregar rounds
                </button>
              </div>

              <div className="round-investigation-grid">
                <div className="card round-search-card">
                  <div className="admin-section-head">
                    <div>
                      <span className="label">Busca</span>
                      <h3>Localizar round</h3>
                    </div>
                  </div>

                  <form className="round-search-form" onSubmit={handleRoundLookupSubmit}>
                    <input
                      type="text"
                      className="form-input"
                      placeholder="Cole um roundId"
                      value={roundLookup}
                      onChange={(event) => setRoundLookup(event.target.value)}
                    />
                    <button type="submit" className="load-btn" disabled={!roundLookup.trim() || isLoadingRoundDetail}>
                      {isLoadingRoundDetail ? 'Buscando...' : 'Buscar'}
                    </button>
                    <button
                      type="button"
                      className="load-btn"
                      onClick={() => {
                        if (currentRound?.roundId) {
                          void handleRoundSelection(currentRound.roundId)
                        }
                      }}
                      disabled={!currentRound?.roundId}
                    >
                      Round atual
                    </button>
                  </form>

                  <div className="round-search-summary">
                    <span>Selecionado</span>
                    <strong>{inspectedRound?.roundId || '--'}</strong>
                    <span>{getRoundStatusLabel(inspectedRound)}</span>
                  </div>
                </div>

                <div className="card round-recent-card">
                  <div className="admin-section-head">
                    <div>
                      <span className="label">Rounds recentes</span>
                      <h3>Navegacao por camera</h3>
                    </div>
                  </div>

                  <div className="round-recent-list">
                    {recentRounds.length === 0 && (
                      <div className="admin-empty">Nenhum round encontrado para a camera.</div>
                    )}

                    {recentRounds.map((item) => (
                      <button
                        key={item.roundId}
                        type="button"
                        className={`round-recent-row${item.roundId === selectedRoundId ? ' is-active' : ''}`}
                        onClick={() => { void handleRoundSelection(item.roundId) }}
                      >
                        <div>
                          <strong>{item.roundId}</strong>
                          <span>{getRoundButtonLabel(item)}</span>
                        </div>
                        <span>{fmtDate(item.createdAt)}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <RoundSummaryCard
                round={inspectedRound}
                title="Round Selecionado"
                locale={embedConfig.locale}
                timezone={embedConfig.timezone}
              />

              <div className="admin-round-detail-grid">
                <div className="card round-markets-card">
                  <div className="admin-section-head">
                    <div>
                      <span className="label">Mercados</span>
                      <h3>Resultado oficial</h3>
                    </div>
                  </div>

                  {selectedRoundMarkets.length === 0 ? (
                    <div className="empty-state">Nenhum mercado associado ao round selecionado.</div>
                  ) : (
                    <div className="round-market-list">
                      {selectedRoundMarkets.map((market) => (
                        <div
                          key={market.marketId || market.id}
                          className={`round-market-row${market.isWinner ? ' is-winner' : ''}`}
                        >
                          <div>
                            <strong>{market.label || market.marketType}</strong>
                            <span>Tipo: {market.marketType || '--'}</span>
                          </div>
                          <div>
                            <strong>{market.targetValue ?? '--'}</strong>
                            <span>{market.isWinner == null ? 'Pendente' : market.isWinner ? 'Vencedor' : 'Nao vencedor'}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="card round-evidence-card">
                  <div className="admin-section-head">
                    <div>
                      <span className="label">Evidencias</span>
                      <h3>Trilha persistida do round</h3>
                    </div>
                  </div>

                  <div className="round-evidence-grid">
                    <div className="round-evidence-stat">
                      <span>Crossings com snapshot</span>
                      <strong>{evidenceEvents.length}</strong>
                    </div>
                    <div className="round-evidence-stat">
                      <span>Status</span>
                      <strong>{getRoundStatusLabel(inspectedRound)}</strong>
                    </div>
                    <div className="round-evidence-stat">
                      <span>Contagem final</span>
                      <strong>{inspectedRound?.finalCount ?? inspectedRound?.currentCount ?? '--'}</strong>
                    </div>
                  </div>

                  {inspectedRound?.voidReason && (
                    <div className="round-summary-void">
                      <span className="label">Motivo do void</span>
                      <strong>{inspectedRound.voidReason}</strong>
                    </div>
                  )}

                  {evidenceEvents.length === 0 ? (
                    <div className="empty-state">Nenhum snapshot persistido para este round.</div>
                  ) : (
                    <div className="round-evidence-list">
                      {evidenceEvents.map((eventItem) => (
                        <a
                          key={eventItem.id || eventItem.eventHash}
                          href={eventItem.snapshotUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="round-evidence-link"
                        >
                          <strong>{eventItem.objectClass || 'veiculo'} #{eventItem.trackId}</strong>
                          <span>{fmtDate(eventItem.timestampUtc)}</span>
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <CrossingEventsCard
                events={roundEvents}
                title="Crossing Events Oficiais"
                locale={embedConfig.locale}
                timezone={embedConfig.timezone}
                limit={20}
                emptyMessage="Nenhum crossing persistido para o round selecionado."
              />

              <RoundTimeline
                items={roundTimeline}
                title="Timeline Investigativa"
                locale={embedConfig.locale}
                timezone={embedConfig.timezone}
                limit={40}
                filter={timelineFilter}
                onFilterChange={setTimelineFilter}
              />

              <div className="admin-history-list official-history-list">
                {filteredHistory.slice(0, 4).map((item) => (
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
