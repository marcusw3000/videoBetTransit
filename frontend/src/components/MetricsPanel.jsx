import { useRef, useEffect, useState } from 'react'

export default function MetricsPanel({ totalCount = 0, lastMinuteCount = 0 }) {
  const historyRef = useRef([])
  const [barPct, setBarPct] = useState(0)

  useEffect(() => {
    const hist = historyRef.current
    hist.push(lastMinuteCount)
    if (hist.length > 10) hist.shift()
    const max = Math.max(...hist, 1)
    setBarPct(Math.round((lastMinuteCount / max) * 100))
  }, [lastMinuteCount])

  return (
    <div className="card metrics-panel">
      <div className="metric-row">
        <span className="metric-label">Total geral</span>
        <span className="metric-value gold">{totalCount.toLocaleString('pt-BR')}</span>
      </div>
      <div className="metric-row" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '0.4rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
          <span className="metric-label">Último minuto</span>
          <span className="metric-value green">+{lastMinuteCount}/min</span>
        </div>
        <div className="minute-bar-track" style={{ width: '100%' }}>
          <div className="minute-bar-fill" style={{ width: `${barPct}%` }} />
        </div>
      </div>
    </div>
  )
}
