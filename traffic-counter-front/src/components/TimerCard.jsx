import { formatTime } from '../utils/time'

export default function TimerCard({ seconds }) {
  return (
    <div className="card stat-card">
      <span className="label">Tempo Restante</span>
      <strong className="big-number">{formatTime(seconds)}</strong>
    </div>
  )
}
