export default function RangeCard({ range }) {
  return (
    <div className="card range-card">
      <h3>{range.label}</h3>
      <p>Odds: {range.odds}</p>
    </div>
  )
}
