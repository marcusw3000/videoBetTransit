import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import { API_BASE_URL, BACKEND_API_KEY, CAMERA_PREVIEW_URL } from '../config'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: BACKEND_API_KEY ? { 'X-API-Key': BACKEND_API_KEY } : {},
})

export default function CameraConfigPage() {
  const previewRef = useRef(null)
  const canvasRef = useRef(null)
  const [isReady, setIsReady] = useState(false)

  const [mode, setMode] = useState('idle')
  const [roi, setRoi] = useState(null)
  const [line, setLine] = useState(null)
  const [direction, setDirection] = useState('any')
  const [cameraId] = useState('cam_001')
  const [previewUrl] = useState(CAMERA_PREVIEW_URL)
  const [message, setMessage] = useState('')

  const drawStart = useRef(null)
  const lineStart = useRef(null)
  const frameSize = useRef({ w: 640, h: 360 })

  useEffect(() => {
    const preview = previewRef.current
    if (!preview) return

    function handleLoad() {
      frameSize.current = {
        w: preview.naturalWidth || 640,
        h: preview.naturalHeight || 360,
      }
      setIsReady(true)
    }

    preview.addEventListener('load', handleLoad)
    return () => preview.removeEventListener('load', handleLoad)
  }, [previewUrl])

  useEffect(() => {
    api.get(`/camera-config/${cameraId}`).then(({ data }) => {
      if (data.roi) setRoi(data.roi)
      if (data.countLine) setLine(data.countLine)
      if (data.countDirection) setDirection(data.countDirection)
    }).catch(() => {})
  }, [cameraId])

  useEffect(() => {
    drawCanvas()
  })

  function getScaledPos(e) {
    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()
    const displayX = e.clientX - rect.left
    const displayY = e.clientY - rect.top
    const { w, h } = frameSize.current

    return {
      x: Math.round((displayX / rect.width) * w),
      y: Math.round((displayY / rect.height) * h),
      displayX,
      displayY,
    }
  }

  function handleMouseDown(e) {
    if (mode === 'roi') {
      drawStart.current = getScaledPos(e)
    }
  }

  function handleMouseMove(e) {
    if (mode === 'roi' && drawStart.current) {
      const pos = getScaledPos(e)
      const startPos = drawStart.current
      const newRoi = {
        x: Math.min(startPos.x, pos.x),
        y: Math.min(startPos.y, pos.y),
        w: Math.abs(pos.x - startPos.x),
        h: Math.abs(pos.y - startPos.y),
      }
      setRoi(newRoi)
    }
  }

  function handleMouseUp() {
    if (mode === 'roi' && drawStart.current) {
      drawStart.current = null
      setMode('idle')
      setMessage('ROI definida! Agora salve ou desenhe a linha.')
    }
  }

  function handleClick(e) {
    if (mode === 'line') {
      const pos = getScaledPos(e)
      if (!lineStart.current) {
        lineStart.current = pos
        setMessage('Clique no ponto final da linha...')
      } else {
        setLine({
          x1: lineStart.current.x,
          y1: lineStart.current.y,
          x2: pos.x,
          y2: pos.y,
        })
        lineStart.current = null
        setMode('idle')
        setMessage('Linha definida! Agora salve.')
      }
    }
  }

  function drawCanvas() {
    const canvas = canvasRef.current
    const preview = previewRef.current
    if (!canvas || !preview) return

    const displayW = preview.clientWidth
    const displayH = preview.clientHeight
    canvas.width = displayW
    canvas.height = displayH

    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, displayW, displayH)

    const { w: fw, h: fh } = frameSize.current
    const sx = (x) => (x / fw) * displayW
    const sy = (y) => (y / fh) * displayH

    if (roi) {
      ctx.strokeStyle = 'rgba(60, 130, 255, 0.8)'
      ctx.lineWidth = 2
      ctx.setLineDash([8, 4])
      ctx.strokeRect(sx(roi.x), sy(roi.y), sx(roi.w), sy(roi.h))
      ctx.setLineDash([])
      ctx.fillStyle = 'rgba(60, 130, 255, 0.1)'
      ctx.fillRect(sx(roi.x), sy(roi.y), sx(roi.w), sy(roi.h))
      ctx.fillStyle = 'rgba(60, 130, 255, 0.9)'
      ctx.font = 'bold 13px Inter, sans-serif'
      ctx.fillText('ROI', sx(roi.x) + 6, sy(roi.y) + 16)
    }

    if (line) {
      ctx.strokeStyle = 'rgba(255, 220, 40, 0.9)'
      ctx.lineWidth = 3
      ctx.beginPath()
      ctx.moveTo(sx(line.x1), sy(line.y1))
      ctx.lineTo(sx(line.x2), sy(line.y2))
      ctx.stroke()

      ctx.fillStyle = 'rgba(255, 220, 40, 0.9)'
      ctx.font = 'bold 12px Inter, sans-serif'
      ctx.fillText('LINHA', sx(line.x1) + 6, sy(line.y1) - 8)
    }

    canvas.style.cursor = mode === 'idle' ? 'default' : 'crosshair'
  }

  async function handleSave() {
    try {
      await api.post(`/camera-config/${cameraId}`, {
        cameraId,
        roi: roi || { x: 0, y: 0, w: 1920, h: 1080 },
        countLine: line || { x1: 0, y1: 360, x2: 1920, y2: 360 },
        countDirection: direction,
      })
      setMessage('Configuracao salva com sucesso!')
    } catch (err) {
      console.error(err)
      setMessage('Falha ao salvar a configuracao.')
    }
  }

  return (
    <div className="page">
      <div className="container">
        <header className="hero">
          <div>
            <h1>Configuracao de Camera</h1>
            <div className="badge">Camera: {cameraId}</div>
          </div>
          <a href="#/" className="primary-button" style={{ textDecoration: 'none', textAlign: 'center' }}>
            Voltar ao Market
          </a>
        </header>

        {message && <div className="info-banner">{message}</div>}

        <div className="config-toolbar">
          <button
            className={`config-btn ${mode === 'roi' ? 'config-btn-active' : ''}`}
            onClick={() => {
              setMode('roi')
              setMessage('Clique e arraste para desenhar a ROI...')
            }}
          >
            Desenhar ROI
          </button>
          <button
            className={`config-btn ${mode === 'line' ? 'config-btn-active' : ''}`}
            onClick={() => {
              setMode('line')
              lineStart.current = null
              setMessage('Clique no ponto inicial da linha...')
            }}
          >
            Desenhar Linha
          </button>

          <select
            className="config-select"
            value={direction}
            onChange={(e) => setDirection(e.target.value)}
          >
            <option value="any">Direcao: Qualquer</option>
            <option value="down">Direcao: Descendo</option>
            <option value="up">Direcao: Subindo</option>
          </select>

          <button className="config-btn config-btn-save" onClick={handleSave}>
            Salvar Configuracao
          </button>
        </div>

        <div className="card video-card" style={{ marginTop: 16 }}>
          <div className="video-frame">
            {!isReady && <div className="video-overlay-message">Carregando preview...</div>}

            <img
              ref={previewRef}
              src={previewUrl}
              alt="Preview da camera"
              className="video-element"
            />

            <canvas
              ref={canvasRef}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: '100%',
                zIndex: 3,
              }}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onClick={handleClick}
            />
          </div>
        </div>

        <div className="config-preview">
          <div className="card" style={{ padding: 16 }}>
            <span className="label">ROI Atual</span>
            <pre>{roi ? JSON.stringify(roi, null, 2) : 'Nao definida'}</pre>
          </div>
          <div className="card" style={{ padding: 16 }}>
            <span className="label">Linha Atual</span>
            <pre>{line ? JSON.stringify(line, null, 2) : 'Nao definida'}</pre>
          </div>
          <div className="card" style={{ padding: 16 }}>
            <span className="label">Direcao</span>
            <pre>{direction}</pre>
          </div>
        </div>
      </div>
    </div>
  )
}
