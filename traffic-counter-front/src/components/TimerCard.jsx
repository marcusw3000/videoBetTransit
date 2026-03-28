import { formatTime } from '../utils/time'

export default function TimerCard({ seconds, label = 'Tempo Restante', tone = 'default' }) {
  return (
    <div className={`card stat-card${tone !== 'default' ? ` timer-card-${tone}` : ''}`}>
      <span className="label">{label}</span>
      <strong className="big-number">{formatTime(seconds)}</strong>
    </div>
  )
}
