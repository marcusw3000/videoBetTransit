export default function DetectionsList({ detections = [] }) {
  const counted = detections
    .filter((d) => d && (d.counted || d.eventHash || d.trackId))
    .slice(0, 8)

  if (counted.length === 0) {
    return (
      <div className="card detections-card">
        <span className="label">Ultimos Carros</span>
        <div className="empty-state">Nenhum carro contabilizado ainda.</div>
      </div>
    )
  }

  return (
    <div className="card detections-card">
      <span className="label">Ultimos Carros Contabilizados</span>
      <div className="detections-grid">
        {counted.map((det) => (
          <div key={det.id || det.eventHash || det.trackId} className="detection-item">
            <span className="detection-type">{det.vehicleType || det.objectClass}</span>
            <span className="detection-id">#{det.trackId}</span>
            <span className="detection-conf">{Math.round((det.confidence ?? 0) * 100)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}
