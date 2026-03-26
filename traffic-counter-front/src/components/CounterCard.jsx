export default function CounterCard({ value }) {
  return (
    <div className="card stat-card">
      <span className="label">Contagem Atual</span>
      <strong className="big-number">{value ?? 0}</strong>
    </div>
  )
}
