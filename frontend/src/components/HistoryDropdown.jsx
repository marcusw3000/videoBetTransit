import { useState } from 'react'
import HistoryCard from './HistoryCard'

export default function HistoryDropdown({
  history = [],
  locale = 'pt-BR',
  timezone = 'America/Sao_Paulo',
  title = 'HISTORICO',
}) {
  const [isOpen, setIsOpen] = useState(false)
  const rounds = Array.isArray(history) ? history : []

  return (
    <section className="card history-dropdown-card">
      <button
        type="button"
        className={`history-dropdown-toggle${isOpen ? ' is-open' : ''}`}
        onClick={() => setIsOpen((value) => !value)}
        aria-expanded={isOpen}
      >
        <div className="history-dropdown-head">
          <span className="label">{title}</span>
          <strong>{rounds.length > 0 ? `${rounds.length} rodada(s)` : 'Sem historico'}</strong>
        </div>
        <span className="history-dropdown-chevron" aria-hidden="true">
          {isOpen ? '▴' : '▾'}
        </span>
      </button>

      {isOpen && (
        <div className="history-dropdown-body">
          {rounds.length === 0 ? (
            <div className="history-dropdown-empty">Nenhum round encerrado ainda.</div>
          ) : (
            <div className="history-dropdown-list">
              {rounds.map((item) => (
                <HistoryCard
                  key={item.roundId || item.id}
                  item={item}
                  locale={locale}
                  timezone={timezone}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
