function formatStatus(value) {
  if (!value) return 'Indisponivel'
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
  const cameraOnline = Boolean(health?.streamConnected)
  const backendOnline = !operations?.backendError && !backend?.lastError
  const feedOnline = streamState === 'online'
  const estimatedLatencyMs = (health?.avgInferenceMs ?? 0) + (health?.avgJpegEncodeMs ?? 0)

  return (
    <div className="card operations-card">
      <div className="operations-header">
        <div>
          <span className="label">Operacao</span>
          <h3>Painel de Saude</h3>
        </div>
        <span className="operations-updated">
          Atualizado em {formatDateTime(operations?.updatedAt)}
        </span>
      </div>

      <div className="operations-pills">
        <StatusPill
          label="Camera"
          status={cameraOnline ? 'Online' : 'Sem stream'}
          tone={cameraOnline ? 'ok' : 'warn'}
        />
        <StatusPill
          label="Backend"
          status={backendOnline ? 'Online' : 'Degradado'}
          tone={backendOnline ? 'ok' : 'warn'}
        />
        <StatusPill
          label="Feed MJPEG"
          status={feedOnline ? 'Transmitindo' : streamState === 'error' ? 'Falhou' : 'Conectando'}
          tone={feedOnline ? 'ok' : streamState === 'error' ? 'error' : 'warn'}
        />
      </div>

      <div className="operations-grid">
        <Metric label="FPS medio" value={formatNumber(health?.fpsAverage)} />
        <Metric label="FPS instantaneo" value={formatNumber(health?.fpsInstant)} />
        <Metric label="Latencia estimada" value={formatNumber(estimatedLatencyMs, ' ms')} />
        <Metric label="Clientes MJPEG" value={health?.mjpegClients ?? 0} />
        <Metric label="Frames processados" value={health?.framesProcessed ?? 0} />
        <Metric label="Total contado" value={health?.totalCount ?? 0} />
      </div>

      <div className="operations-footer">
        <div className="ops-event">
          <span className="ops-footer-label">Ultimo evento recebido</span>
          <strong>{lastEvent?.label ?? 'Aguardando eventos em tempo real'}</strong>
          <span>{formatDateTime(lastEvent?.at)}</span>
        </div>

        <div className="ops-event">
          <span className="ops-footer-label">Ultima atividade do backend</span>
          <strong>{backend?.lastError ? 'Com falha recente' : 'Sem falhas recentes'}</strong>
          <span>{formatDateTime(backend?.lastSuccessAt || backend?.lastErrorAt)}</span>
        </div>
      </div>
    </div>
  )
}
