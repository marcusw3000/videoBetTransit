function Sparkline({ history }) {
  if (!history || history.length < 2) return null

  const W = 220
  const H = 44
  const max = Math.max(...history, 1)
  const points = history
    .map((val, i) => {
      const x = (i / (history.length - 1)) * W
      const y = H - (val / max) * (H - 4) - 2
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      className="sparkline"
      aria-hidden="true"
    >
      <polyline
        points={points}
        fill="none"
        stroke="rgba(160,160,220,0.65)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* dot no último ponto */}
      {(() => {
        const last = history[history.length - 1]
        const x = W
        const y = H - (last / max) * (H - 4) - 2
        return <circle cx={x} cy={y} r="3" fill="rgba(180,180,255,0.9)" />
      })()}
    </svg>
  )
}

export default function CounterCard({ value, history }) {
  return (
    <div className="card stat-card">
      <span className="label">Contagem Atual</span>
      <strong className="big-number">{value ?? 0}</strong>
      <Sparkline history={history} />
    </div>
  )
}
