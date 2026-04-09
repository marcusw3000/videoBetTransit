function formatDateTime(value, locale = 'pt-BR', timezone = 'America/Sao_Paulo') {
  if (!value) return '--'

  try {
    return new Date(value).toLocaleString(locale, {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      timeZone: timezone,
    })
  } catch {
    return value
  }
}

export default function RoundSummaryCard({
  round,
  title = 'Round Oficial',
  locale = 'pt-BR',
  timezone = 'America/Sao_Paulo',
  compact = false,
}) {
  const metaClassName = compact ? 'round-summary-meta round-summary-meta-compact' : 'round-summary-meta'
  const status = String(round?.status || 'loading').toLowerCase()
  const roundMode = String(round?.roundMode || 'normal').toLowerCase()
  const cardClassName = `card round-summary-card${roundMode === 'turbo' ? ' round-summary-card-turbo' : ''}`

  return (
    <div className={cardClassName}>
      <div className="round-summary-head">
        <div>
          <span className="label">{title}</span>
          <h3>{round?.displayName || 'Rodada Normal'}</h3>
        </div>
        <div className="round-summary-head-badges">
          {roundMode === 'turbo' && (
            <span className="turbo-badge round-summary-mode-turbo">TURBO</span>
          )}
          <span className={`admin-round-status admin-round-status-${status}`}>
            {status.toUpperCase()}
          </span>
        </div>
      </div>

      <div className={metaClassName}>
        <div>
          <span className="label">Round ID</span>
          <strong className="round-summary-id">{round?.roundId || '--'}</strong>
        </div>
        <div>
          <span className="label">Camera</span>
          <strong>{round?.cameraId || '--'}</strong>
        </div>
        <div>
          <span className="label">Modo</span>
          <strong>{roundMode === 'turbo' ? 'Turbo' : 'Normal'}</strong>
        </div>
        <div>
          <span className="label">Criado em</span>
          <strong>{formatDateTime(round?.createdAt, locale, timezone)}</strong>
        </div>
        <div>
          <span className="label">Fecha apostas</span>
          <strong>{formatDateTime(round?.betCloseAt, locale, timezone)}</strong>
        </div>
        <div>
          <span className="label">Encerra em</span>
          <strong>{formatDateTime(round?.endsAt, locale, timezone)}</strong>
        </div>
        <div>
          <span className="label">Liquidado em</span>
          <strong>{formatDateTime(round?.settledAt, locale, timezone)}</strong>
        </div>
        <div>
          <span className="label">Anulado em</span>
          <strong>{formatDateTime(round?.voidedAt, locale, timezone)}</strong>
        </div>
        <div>
          <span className="label">Contagem atual</span>
          <strong>{round?.currentCount ?? 0}</strong>
        </div>
        <div>
          <span className="label">Contagem final</span>
          <strong>{round?.finalCount ?? '--'}</strong>
        </div>
      </div>

      {round?.voidReason && (
        <div className="round-summary-void">
          <span className="label">Motivo do void</span>
          <strong>{round.voidReason}</strong>
        </div>
      )}
    </div>
  )
}
