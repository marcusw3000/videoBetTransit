const DIR_ICON = {
  up_to_down: '↓',
  down_to_up: '↑',
  left_to_right: '→',
  right_to_left: '←',
  any: '↕',
}

function dirIcon(direction) {
  return DIR_ICON[direction] || '↕'
}

export default function EventsFeed({ events = [] }) {
  return (
    <div className="card events-section">
      <div className="section-title">Cruzamentos recentes</div>
      {events.length === 0 ? (
        <span className="events-empty">Aguardando eventos...</span>
      ) : (
        <div className="events-list">
          {events.map((ev, index) => (
            <div
              className="event-chip"
              key={ev.id ?? ev.eventHash ?? `${ev.trackId ?? 'track'}-${ev.frameNumber ?? index}`}
            >
              <span className="event-chip-dir">{dirIcon(ev.direction)}</span>
              <span className="event-chip-class">{ev.objectClass}</span>
              <span className="event-chip-id">#{ev.trackId}</span>
              <span className="event-chip-conf">{Math.round((ev.confidence ?? 0) * 100)}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
