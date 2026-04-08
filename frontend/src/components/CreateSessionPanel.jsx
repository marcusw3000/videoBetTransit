import { useState } from 'react'
import { createSession, startSession } from '../services/streamApi'
import LiveBadge from './LiveBadge'

const DEFAULT_LINE = { x1: 300, y1: 346, x2: 601, y2: 288 }

function fmt(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export default function CreateSessionPanel({ onSessionCreated, recentSessions = [] }) {
  const [form, setForm] = useState({
    cameraName: '',
    sourceUrl: '',
    protocol: 'Rtsp',
    direction: 'down_to_up',
    x1: DEFAULT_LINE.x1,
    y1: DEFAULT_LINE.y1,
    x2: DEFAULT_LINE.x2,
    y2: DEFAULT_LINE.y2,
  })
  const [loadId, setLoadId] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const payload = {
        cameraName: form.cameraName,
        sourceUrl: form.sourceUrl,
        protocol: form.protocol,
        countDirection: form.direction,
        countLine: {
          x1: Number(form.x1),
          y1: Number(form.y1),
          x2: Number(form.x2),
          y2: Number(form.y2),
        },
      }
      const { data: session } = await createSession(payload)
      await startSession(session.id)
      sessionStorage.setItem('sessionId', session.id)
      onSessionCreated(session.id)
    } catch (err) {
      const msg = err?.response?.data?.message || err?.response?.data || err.message || 'Erro desconhecido'
      setError(String(msg))
    } finally {
      setLoading(false)
    }
  }

  async function handleLoad(e) {
    e.preventDefault()
    if (!loadId.trim()) return
    sessionStorage.setItem('sessionId', loadId.trim())
    onSessionCreated(loadId.trim())
  }

  return (
    <>
      {recentSessions.length > 0 && (
        <div className="card create-panel" style={{ marginBottom: '0' }}>
          <div className="create-panel-title">◆ Sessões Ativas</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {recentSessions.map((s) => (
              <div
                key={s.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.6rem 0.75rem',
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid var(--bg-card-border)',
                  borderRadius: '8px',
                  gap: '0.75rem',
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem', overflow: 'hidden' }}>
                  <span style={{ fontWeight: 700, fontSize: '0.82rem', color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {s.cameraName || 'Câmera sem nome'}
                  </span>
                  <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
                    {fmt(s.startedAt || s.createdAt)}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexShrink: 0 }}>
                  <LiveBadge status={s.status} />
                  <button
                    className="load-btn"
                    style={{ padding: '0.35rem 0.75rem', fontSize: '0.72rem' }}
                    onClick={() => {
                      sessionStorage.setItem('sessionId', s.id)
                      onSessionCreated(s.id)
                    }}
                  >
                    Retomar
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <form className="card create-panel" onSubmit={handleSubmit}>
        <div className="create-panel-title">◆ Nova Sessão</div>

        <div className="form-group">
          <label className="form-label">Nome da câmera</label>
          <input className="form-input" value={form.cameraName} onChange={set('cameraName')} required placeholder="Ex: Rodovia Norte" />
        </div>

        <div className="form-group">
          <label className="form-label">URL do stream</label>
          <input className="form-input" value={form.sourceUrl} onChange={set('sourceUrl')} required placeholder="rtsp://..." />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Protocolo</label>
            <select className="form-select" value={form.protocol} onChange={set('protocol')}>
              <option value="Rtsp">RTSP</option>
              <option value="Rtmp">RTMP</option>
              <option value="Hls">HLS</option>
              <option value="Srt">SRT</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Direção de contagem</label>
            <select className="form-select" value={form.direction} onChange={set('direction')}>
              <option value="down_to_up">De baixo para cima</option>
              <option value="up_to_down">De cima para baixo</option>
              <option value="left_to_right">Esquerda para direita</option>
              <option value="right_to_left">Direita para esquerda</option>
              <option value="any">Qualquer</option>
            </select>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Linha de contagem</label>
          <div className="form-row">
            <div>
              <label className="form-label" style={{ fontSize: '0.6rem' }}>X1</label>
              <input className="form-input" type="number" value={form.x1} onChange={set('x1')} />
            </div>
            <div>
              <label className="form-label" style={{ fontSize: '0.6rem' }}>Y1</label>
              <input className="form-input" type="number" value={form.y1} onChange={set('y1')} />
            </div>
          </div>
          <div className="form-row" style={{ marginTop: '0.5rem' }}>
            <div>
              <label className="form-label" style={{ fontSize: '0.6rem' }}>X2</label>
              <input className="form-input" type="number" value={form.x2} onChange={set('x2')} />
            </div>
            <div>
              <label className="form-label" style={{ fontSize: '0.6rem' }}>Y2</label>
              <input className="form-input" type="number" value={form.y2} onChange={set('y2')} />
            </div>
          </div>
        </div>

        {error && <div className="form-error">{error}</div>}

        <button className="submit-btn" type="submit" disabled={loading}>
          {loading ? 'Iniciando...' : '◆ Iniciar Sessão'}
        </button>
      </form>

      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.75rem', width: '100%', maxWidth: '520px' }}>
        <span className="divider-text">— ou carregue uma sessão existente —</span>
        <form className="load-session-row" onSubmit={handleLoad}>
          <input
            className="form-input"
            value={loadId}
            onChange={(e) => setLoadId(e.target.value)}
            placeholder="Session ID..."
          />
          <button className="load-btn" type="submit">Carregar</button>
        </form>
      </div>
    </>
  )
}
