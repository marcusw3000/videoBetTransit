function formatDateTime(value) {
  if (!value) return 'agora'

  const parsed = Number.isFinite(value) ? new Date(value * 1000) : new Date(value)
  if (Number.isNaN(parsed.getTime())) return 'agora'

  return parsed.toLocaleString('pt-BR')
}

function AlertItem({ alert }) {
  return (
    <div className={`alert-item alert-item-${alert.severity}`}>
      <div className="alert-item-header">
        <strong>{alert.title}</strong>
        <span>{alert.badge}</span>
      </div>
      <p>{alert.message}</p>
      <small>Último sinal: {formatDateTime(alert.at)}</small>
    </div>
  )
}

export default function AlertsPanel({ alerts }) {
  if (!alerts.length) {
    return (
      <div className="card alerts-card">
        <div className="alerts-header">
          <div>
            <span className="label">Alertas</span>
            <h3>Monitoramento</h3>
          </div>
        </div>

        <div className="alerts-empty">
          Nenhum alerta operacional ativo no momento.
        </div>
      </div>
    )
  }

  return (
    <div className="card alerts-card">
      <div className="alerts-header">
        <div>
          <span className="label">Alertas</span>
          <h3>Monitoramento</h3>
        </div>
        <span className="alerts-counter">{alerts.length} ativo(s)</span>
      </div>

      <div className="alerts-list">
        {alerts.map((alert) => (
          <AlertItem key={alert.id} alert={alert} />
        ))}
      </div>
    </div>
  )
}
