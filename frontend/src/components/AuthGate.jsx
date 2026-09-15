import { createContext, useContext, useEffect, useState } from 'react'
import { api, clearCsrf } from '../services/apiClient'

const SessionContext = createContext(null)
// eslint-disable-next-line react-refresh/only-export-components
export function useSession() { return useContext(SessionContext) }

export default function AuthGate({ children, admin = false }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let active = true
    api.get('/auth/me').then(({ data }) => { if (active) setUser(data) })
      .catch(() => {}).finally(() => { if (active) setLoading(false) })
    const expire = () => { clearCsrf(); setUser(null) }
    window.addEventListener('session:expired', expire)
    return () => { active = false; window.removeEventListener('session:expired', expire) }
  }, [])

  async function login(event) {
    event.preventDefault()
    const values = new FormData(event.currentTarget)
    setBusy(true); setError('')
    try {
      const { data } = await api.post('/auth/login', Object.fromEntries(values))
      clearCsrf(); setUser(data)
    } catch (err) { setError(err.response?.status === 429 ? 'Muitas tentativas. Aguarde um minuto.' : err.response?.data?.error || 'Nao foi possivel entrar.') }
    finally { setBusy(false) }
  }
  async function logout() {
    try { await api.post('/auth/logout'); clearCsrf(); setUser(null) }
    catch { setError('Nao foi possivel sair. Tente novamente.') }
  }
  if (loading) return <p className="session-card" role="status">Carregando sessao...</p>
  if (!user) return <main className="session-card">
    <h1>VideoBetTransit</h1><p>Demonstracao · sem movimentacao financeira</p>
    <form onSubmit={login}>
      <label>Usuario<input name="Username" autoComplete="username" required maxLength={128} /></label>
      <label>Senha<input name="Password" type="password" autoComplete="current-password" required maxLength={1024} /></label>
      <button disabled={busy}>{busy ? 'Entrando...' : 'Entrar'}</button>
    </form>
    {error && <p role="alert">{error}</p>}
  </main>
  return <SessionContext.Provider value={user}>
    <div className="session-bar"><span>{user.username} · Demonstracao sem dinheiro real</span><button onClick={logout}>Sair</button></div>
    {error && <p role="alert">{error}</p>}
    {admin && user.role !== 'admin' ? <p className="session-card">Acesso restrito a administradores. <a href="/">Voltar</a></p> : children}
  </SessionContext.Provider>
}
