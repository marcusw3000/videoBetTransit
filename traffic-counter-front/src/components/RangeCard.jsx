export default function RangeCard({ range, isActive }) {
  return (
    <div className={`card range-card${isActive ? ' range-card-active' : ''}`}>
      <h3>{range.label}</h3>
      <p className="range-odds">{range.odds}x</p>
      {isActive && <span className="range-active-badge">AO VIVO</span>}
    </div>
  )
}
