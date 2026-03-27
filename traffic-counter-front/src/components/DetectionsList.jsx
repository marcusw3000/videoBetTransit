export default function DetectionsList({ detections = [] }) {
  // Mostra os últimos 8 veículos que cruzaram a linha (counted)
  const counted = detections.filter(d => d.counted).slice(-8).reverse()

  if (counted.length === 0) {
    return (
      <div className="card detections-card">
        <span className="label">Últimos Veículos</span>
        <div className="empty-state">Nenhum veículo contabilizado ainda.</div>
      </div>
    )
  }

  return (
    <div className="card detections-card">
      <span className="label">Últimos Contabilizados</span>
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
