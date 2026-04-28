function formatStatus(value) {
  if (!value) return 'Indisponível'
  return value
}

function formatNumber(value, suffix = '') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '--'
  }

  return `${Number(value).toFixed(1)}${suffix}`
}

function formatDateTime(value) {
  if (!value) return 'Aguardando evento'

  const parsed = Number.isFinite(value) ? new Date(value * 1000) : new Date(value)
  if (Number.isNaN(parsed.getTime())) return 'Aguardando evento'

  return parsed.toLocaleString('pt-BR')
}

function StatusPill({ label, status, tone }) {
  return (
    <div className={`ops-pill ops-pill-${tone}`}>
      <span className="ops-pill-label">{label}</span>
      <strong>{formatStatus(status)}</strong>
    </div>
  )
}

function Metric({ label, value }) {
  return (
    <div className="ops-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

export default function OperationsCard({
  operations,
  streamState,
  lastEvent,
}) {
  const health = operations?.health ?? null
  const backend = health?.backend ?? {}
  const captureOnline = Boolean(health?.streamConnected)
  const backendOnline = !operations?.backendError && !backend?.lastError
  const publisherOnline = Boolean(health?.publisherHealthy)
  const transportMode = String(health?.activeTransport || 'mjpeg').toUpperCase()
  const frontendOnline = streamState === 'online'
  const fallbackActive = transportMode !== 'WEBRTC'
  const estimatedLatencyMs = (health?.avgInferenceMs ?? 0) + (health?.avgJpegEncodeMs ?? 0)
  const frontendAckPhase = String(health?.frontendAckPhase || '').trim().toLowerCase()
  const activation = health?.cameraActivation || {}
  const frontendAckStatus = frontendAckPhase === 'frontend_pending'
    ? 'Aguardando player publico'
    : frontendAckPhase === 'requested'
      ? 'Aguardando stream pronta'
      : frontendAckPhase === 'ready'
        ? 'Liberado'
        : '--'

  return (
    <div className="card operations-card">
      <div className="operations-header">
        <div>
          <span className="label">Operação</span>
          <h3>Painel de Saúde</h3>
        </div>
        <span className="operations-updated">
          Atualizado em {formatDateTime(operations?.updatedAt)}
        </span>
      </div>

      <div className="operations-pills">
        <StatusPill
          label="Captura"
          status={captureOnline ? 'Online' : 'Sem stream'}
          tone={captureOnline ? 'ok' : 'warn'}
        />
        <StatusPill
          label="Publisher RTSP"
          status={publisherOnline ? 'Publicando' : 'Parado'}
          tone={publisherOnline ? 'ok' : 'warn'}
        />
        <StatusPill
          label="Frontend"
          status={frontendOnline ? 'Transmitindo' : streamState === 'error' ? 'Falhou' : 'Conectando'}
          tone={frontendOnline ? 'ok' : streamState === 'error' ? 'error' : 'warn'}
        />
        <StatusPill
          label="Transporte"
          status={fallbackActive ? `${transportMode} (fallback)` : transportMode}
          tone={fallbackActive ? 'warn' : 'ok'}
        />
      </div>

      <div className="operations-grid">
        <Metric label="FPS captura" value={formatNumber(health?.captureFps)} />
        <Metric label="FPS inferência" value={formatNumber(health?.inferenceFps ?? health?.fpsAverage)} />
        <Metric label="FPS publicação" value={formatNumber(health?.publishFps)} />
        <Metric label="Latência estimada" value={formatNumber(estimatedLatencyMs, ' ms')} />
        <Metric label="Idade frame bruto" value={formatNumber(health?.rawFrameAgeMs, ' ms')} />
        <Metric label="Idade frame anotado" value={formatNumber(health?.annotatedFrameAgeMs, ' ms')} />
      </div>

      <div className="operations-grid">
        <Metric label="Clientes MJPEG" value={health?.mjpegClients ?? 0} />
        <Metric label="Frames processados" value={health?.framesProcessed ?? 0} />
        <Metric label="Reinícios publisher" value={health?.publisherRestartCount ?? 0} />
        <Metric label="Backend" value={backendOnline ? 'Online' : 'Degradado'} />
        <Metric label="Contagem worker" value={health?.totalCount ?? 0} />
        <Metric label="Último publish" value={formatDateTime(health?.lastPublishAt)} />
        <Metric label="Gate round" value={frontendAckStatus} />
      </div>
      <div className="operations-grid">
        <Metric label="Sessao ativacao" value={activation?.activationSessionId || '--'} />
        <Metric label="Ativacao pedida" value={formatDateTime(activation?.activationRequestedAt)} />
        <Metric label="1o frame capturado" value={formatDateTime(activation?.firstCaptureAt)} />
        <Metric label="1o frame renderizavel" value={formatDateTime(activation?.firstRenderableFrameAt)} />
        <Metric label="1o frame publicado" value={formatDateTime(activation?.firstPublishedAt)} />
        <Metric label="Ultima sessao renderizada" value={activation?.lastRenderableActivationSessionId || '--'} />
      </div>
      <div className="operations-footer">
        <div className="ops-event">
          <span className="ops-footer-label">Último evento recebido</span>
          <strong>{lastEvent?.label ?? 'Aguardando eventos em tempo real'}</strong>
          <span>{formatDateTime(lastEvent?.at)}</span>
        </div>

        <div className="ops-event">
          <span className="ops-footer-label">Última atividade do backend</span>
          <strong>{backend?.lastError ? 'Com falha recente' : 'Sem falhas recentes'}</strong>
          <span>{formatDateTime(backend?.lastSuccessAt || backend?.lastErrorAt)}</span>
        </div>
      </div>
    </div>
  )
}
