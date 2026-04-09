export default function DetectionsList({ detections = [] }) {
  const counted = detections.filter((d) => d.counted).slice(-8).reverse()

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
          <div key={det.trackId} className="detection-item">
            <span className="detection-type">{det.vehicleType}</span>
            <span className="detection-id">#{det.trackId}</span>
            <span className="detection-conf">{Math.round(det.confidence * 100)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}
