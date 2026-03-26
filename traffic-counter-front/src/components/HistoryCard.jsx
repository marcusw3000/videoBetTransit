export default function HistoryCard({ item }) {
  return (
    <div className="card history-card">
      <div>
        <strong>{item.id}</strong>
      </div>
      <div>Status: {item.status}</div>
      <div>Final: {item.finalCount ?? '-'}</div>
    </div>
  )
}
