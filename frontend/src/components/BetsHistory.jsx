import { useCallback, useEffect, useState } from 'react'
import { listBets } from '../services/betApi'

const statuses = { accepted: 'Em aberto', settled_win: 'Ganhou', settled_loss: 'Perdeu', void: 'Anulada', rollback: 'Estornada' }
export default function BetsHistory({ locale = 'pt-BR' }) {
  const [status, setStatus] = useState('all')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const [result, setResult] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const reload = useCallback(() => setRefresh(value => value + 1), [])
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    listBets({ status, page, pageSize: 10,
      from: from ? new Date(`${from}T00:00:00`).toISOString() : undefined,
      to: to ? new Date(`${to}T23:59:59.999`).toISOString() : undefined,
    }, controller.signal).then(data => { if (active) { setResult(data); setError(''); if (page > Math.max(1, Math.ceil(data.total / 10))) setPage(Math.max(1, Math.ceil(data.total / 10))) } })
      .catch(err => { if (active && err.code !== 'ERR_CANCELED') setError('Nao foi possivel carregar suas apostas.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false; controller.abort() }
  }, [status, from, to, page, refresh])
  useEffect(() => {
    const timer = setInterval(reload, 10000)
    window.addEventListener('bets:changed', reload)
    return () => { clearInterval(timer); window.removeEventListener('bets:changed', reload) }
  }, [reload])
  function changeFilter(setter, value) { setter(value); setPage(1); setLoading(true) }
  return <section className="positions-section" aria-label="Minhas apostas">
    <h2 className="positions-title">Minhas posições</h2>
    <div className="positions-tabs">{[['all', 'Todas'], ['open', 'Em aberto'], ['closed', 'Encerradas']].map(([key, label]) =>
      <button key={key} aria-pressed={status === key} className={`positions-tab${status === key ? ' positions-tab-active' : ''}`} onClick={() => changeFilter(setStatus, key)}>{label}</button>)}</div>
    <div className="positions-dates"><label>De<input type="date" value={from} onChange={e => changeFilter(setFrom, e.target.value)} /></label>
      <label>Até<input type="date" value={to} min={from || undefined} onChange={e => changeFilter(setTo, e.target.value)} /></label></div>
    {error ? <p role="alert">{error} <button onClick={reload}>Tentar novamente</button></p>
      : loading ? <p role="status">Carregando apostas...</p>
        : result.items.length === 0 ? <p>Nenhuma aposta neste filtro.</p>
          : <ul className="positions-list">{result.items.map(bet => <li key={bet.id}>
            <strong>{bet.marketLabel}</strong><br />
            {new Intl.NumberFormat(locale, { style: 'currency', currency: bet.currency }).format(bet.stakeAmount)} · {statuses[bet.status] || bet.status}<br />
            <small>{new Date(bet.placedAt).toLocaleString(locale)}</small>
          </li>)}</ul>}
    <div className="positions-pagination"><button disabled={page === 1 || loading} onClick={() => { setPage(page - 1); setLoading(true) }}>Anterior</button>
      <span>Página {page} de {Math.max(1, Math.ceil(result.total / 10))}</span>
      <button disabled={page * 10 >= result.total || loading} onClick={() => { setPage(page + 1); setLoading(true) }}>Próxima</button></div>
  </section>
}
