import { useCallback, useEffect, useRef, useState } from 'react'
import { activateCameraManagement, applyCameraManagement, deactivateCameraManagement, getCameraManagement, updateCameraManagementDraft } from '../services/cameraManagementApi'

export default function CameraManagementCard({ cameraId, streamProfileId }) {
  const [state, setState] = useState(null)
  const [reason, setReason] = useState('')
  const [draft, setDraft] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [draftRevision, setDraftRevision] = useState(null)
  const dirtyRef = useRef(false)
  const busyRef = useRef(false)
  const requestEpochRef = useRef(0)
  const mountedRef = useRef(false)
  const reload = useCallback(async (force = false) => {
    const epoch = requestEpochRef.current
    const next = (await getCameraManagement()).data
    if (!mountedRef.current || epoch !== requestEpochRef.current) return
    setState(next)
    if (force || !dirtyRef.current || !next.isActive) {
      try { setDraft(next.draftConfigurationJson ? JSON.parse(next.draftConfigurationJson) : null) } catch { setDraft(null) }
      setDraftRevision(next.revision)
      dirtyRef.current = false
    }
  }, [])
  useEffect(() => {
    let mounted = true
    let timerId
    mountedRef.current = true
    const refresh = async () => {
      try { if (!busyRef.current) await reload() }
      catch { if (mounted) setError('Não foi possível consultar o modo de gerenciamento.') }
      if (mounted) timerId = setTimeout(() => void refresh(), 3000)
    }
    void refresh()
    return () => { mounted = false; mountedRef.current = false; requestEpochRef.current += 1; clearTimeout(timerId) }
  }, [reload])
  const run = async (action) => {
    if (busyRef.current) return
    busyRef.current = true
    requestEpochRef.current += 1
    setBusy(true)
    setError('')
    try { await action(); await reload(true) }
    catch (e) { if (mountedRef.current) setError(e?.response?.data?.error || 'Ação não concluída.') }
    finally { busyRef.current = false; if (mountedRef.current) setBusy(false) }
  }
  const active = Boolean(state?.isActive)
  return <section className={`card camera-management-card${active ? ' is-active' : ''}`}>
    <div className="admin-section-head"><div><span className="label">Gerenciamento de câmera</span><h3>{active ? 'Calibração em andamento' : 'Operação normal'}</h3></div><strong>{active ? 'ROUNDS PAUSADOS' : 'PRONTO'}</strong></div>
    <p>{active ? 'A câmera e o perfil estão fixos. A contagem atual é somente de teste e não gera eventos oficiais.' : 'Ative para calibrar ROI e linha sem trocar câmera ou iniciar novos rounds.'}</p>
    {error && <div className="error-banner">{error}</div>}
    {!active && <><input className="form-input" value={reason} maxLength={512} onChange={e => setReason(e.target.value)} placeholder="Justificativa para entrar no modo" />
      <button className="load-btn" disabled={busy || !reason.trim() || !cameraId || !streamProfileId} onClick={() => run(() => activateCameraManagement({ reason: reason.trim(), cameraId, streamProfileId }))}>{busy ? 'Ativando...' : 'Ativar gerenciamento'}</button></>}
    {active && <div className="camera-management-actions"><p>Revisão da calibração: <strong>{state.revision}</strong> · {state.draftApplied ? 'aplicada' : 'com alterações pendentes'}</p>
      {draft && <div className="camera-management-geometry">{[['ROI', 'roi', ['x','y','w','h']], ['Linha', 'line', ['x1','y1','x2','y2']]].map(([label, key, fields]) => <fieldset key={key}><legend>{label}</legend>{fields.map(field => <label key={field}>{field}<input type="number" disabled={busy} value={draft[key]?.[field] ?? 0} onChange={e => { dirtyRef.current = true; setDraft({ ...draft, [key]: { ...draft[key], [field]: Number(e.target.value) } }) }} /></label>)}</fieldset>)}
        <button className="load-btn" disabled={busy} onClick={() => run(() => updateCameraManagementDraft({ expectedRevision: draftRevision, roi: draft.roi, line: draft.line }))}>Atualizar preview de teste</button></div>}
      <button className="load-btn" disabled={busy || state.draftApplied} onClick={() => run(applyCameraManagement)}>Aplicar calibração</button>
      <button className="admin-danger-btn" disabled={busy || !state.draftApplied} onClick={() => run(deactivateCameraManagement)}>Aplicar e retomar operação</button></div>}
  </section>
}
