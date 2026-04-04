export default function LiveBadge({ status }) {
  const s = (status || '').toLowerCase()

  const labels = {
    running:   '● AO VIVO',
    degraded:  '◐ DEGRADADO',
    starting:  '○ INICIANDO',
    ready:     '○ PRONTO',
    failed:    '✕ FALHA',
    stopped:   '■ PARADO',
  }

  const label = labels[s] || `○ ${status || '—'}`
  const cls = ['running', 'degraded', 'starting', 'ready', 'failed', 'stopped'].includes(s)
    ? s
    : 'default'

  return (
    <span className={`live-badge ${cls}`}>
      <span className="live-dot" />
      {label}
    </span>
  )
}
