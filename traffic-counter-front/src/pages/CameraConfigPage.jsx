import { useEffect, useRef, useState } from 'react'
import Hls from 'hls.js'
import axios from 'axios'

const api = axios.create({ baseURL: 'http://localhost:5000/api' })

/**
 * Página admin para configurar ROI e linha de contagem por câmera.
 * O admin pode:
 * - Desenhar ROI arrastando o mouse (click + drag)
 * - Desenhar linha de contagem com 2 cliques
 * - Salvar a configuração
 */
export default function CameraConfigPage() {
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const [isReady, setIsReady] = useState(false)

  const [mode, setMode] = useState('idle') // 'idle' | 'roi' | 'line'
  const [roi, setRoi] = useState(null)
  const [line, setLine] = useState(null)
  const [direction, setDirection] = useState('any')
  const [cameraId] = useState('cam_001')
  const [streamUrl] = useState('https://34.104.32.249.nip.io/SP125-KM093B/stream.m3u8')
  const [message, setMessage] = useState('')

  // Temporários para desenho
  const drawStart = useRef(null)
  const lineStart = useRef(null)

  // Tamanho real do frame (detectado pelo vídeo)
  const frameSize = useRef({ w: 640, h: 360 })

  // HLS setup
  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    let hls = null

    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = streamUrl
      video.addEventListener('loadedmetadata', () => {
        frameSize.current = { w: video.videoWidth, h: video.videoHeight }
        setIsReady(true)
        video.play().catch(() => {})
      }, { once: true })
    } else if (Hls.isSupported()) {
      hls = new Hls({ enableWorker: true, lowLatencyMode: true })
      hls.loadSource(streamUrl)
      hls.attachMedia(video)
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        setIsReady(true)
        video.play().catch(() => {})
        // Espera um pouco para pegar videoWidth/videoHeight
        setTimeout(() => {
          frameSize.current = { w: video.videoWidth || 640, h: video.videoHeight || 360 }
        }, 500)
      })
    }

    return () => { if (hls) hls.destroy() }
  }, [streamUrl])

  // Carregar config existente
  useEffect(() => {
    api.get(`/camera-config/${cameraId}`).then(({ data }) => {
      if (data.roi) setRoi(data.roi)
      if (data.countLine) setLine(data.countLine)
      if (data.countDirection) setDirection(data.countDirection)
    }).catch(() => {})
  }, [cameraId])

  // Redesenha canvas quando ROI ou linha mudam
  useEffect(() => {
    drawCanvas()
  })

  function getScaledPos(e) {
    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()
    const displayX = e.clientX - rect.left
    const displayY = e.clientY - rect.top
    const { w, h } = frameSize.current
    // Converte de coordenadas do display para coordenadas do frame
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
    const video = videoRef.current
    if (!canvas || !video) return

    const displayW = video.clientWidth
    const displayH = video.clientHeight
    canvas.width = displayW
    canvas.height = displayH

    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, displayW, displayH)

    const { w: fw, h: fh } = frameSize.current
    const sx = (x) => (x / fw) * displayW
    const sy = (y) => (y / fh) * displayH

    // Desenha ROI
    if (roi) {
      ctx.strokeStyle = 'rgba(60, 130, 255, 0.8)'
      ctx.lineWidth = 2
      ctx.setLineDash([8, 4])
      ctx.strokeRect(sx(roi.x), sy(roi.y), sx(roi.w), sy(roi.h))
      ctx.setLineDash([])
      ctx.fillStyle = 'rgba(60, 130, 255, 0.1)'
      ctx.fillRect(sx(roi.x), sy(roi.y), sx(roi.w), sy(roi.h))

      // Label
      ctx.fillStyle = 'rgba(60, 130, 255, 0.9)'
      ctx.font = 'bold 13px Inter, sans-serif'
      ctx.fillText('ROI', sx(roi.x) + 6, sy(roi.y) + 16)
    }

    // Desenha Linha
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

    // Cursor mode indicator
    if (mode === 'roi') {
      canvas.style.cursor = 'crosshair'
    } else if (mode === 'line') {
      canvas.style.cursor = 'crosshair'
    } else {
      canvas.style.cursor = 'default'
    }
  }

  async function handleSave() {
    try {
      await api.post(`/camera-config/${cameraId}`, {
        cameraId,
        roi: roi || { x: 0, y: 0, w: 1920, h: 1080 },
        countLine: line || { x1: 0, y1: 360, x2: 1920, y2: 360 },
        countDirection: direction,
      })
      setMessage('✅ Configuração salva!')
    } catch (err) {
      console.error(err)
      setMessage('❌ Falha ao salvar.')
    }
  }

  return (
    <div className="page">
      <div className="container">
        <header className="hero">
          <div>
            <h1>Configuração de Câmera</h1>
            <div className="badge">Câmera: {cameraId}</div>
          </div>
          <a href="#/" className="primary-button" style={{ textDecoration: 'none', textAlign: 'center' }}>
            ← Voltar ao Market
          </a>
        </header>

        {message && <div className="info-banner">{message}</div>}

        {/* Toolbar */}
        <div className="config-toolbar">
          <button
            className={`config-btn ${mode === 'roi' ? 'config-btn-active' : ''}`}
            onClick={() => { setMode('roi'); setMessage('Clique e arraste para desenhar a ROI...') }}
          >
            📐 Desenhar ROI
          </button>
          <button
            className={`config-btn ${mode === 'line' ? 'config-btn-active' : ''}`}
            onClick={() => { setMode('line'); lineStart.current = null; setMessage('Clique no ponto inicial da linha...') }}
          >
            ✏️ Desenhar Linha
          </button>

          <select
            className="config-select"
            value={direction}
            onChange={(e) => setDirection(e.target.value)}
          >
            <option value="any">Direção: Qualquer</option>
            <option value="down">Direção: Descendo ↓</option>
            <option value="up">Direção: Subindo ↑</option>
          </select>

          <button className="config-btn config-btn-save" onClick={handleSave}>
            💾 Salvar Configuração
          </button>
        </div>

        {/* Video + Canvas */}
        <div className="card video-card" style={{ marginTop: 16 }}>
          <div className="video-frame">
            {!isReady && <div className="video-overlay-message">Carregando stream...</div>}

            <video
              ref={videoRef}
              className="video-element"
              muted
              autoPlay
              playsInline
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

        {/* Config preview */}
        <div className="config-preview">
          <div className="card" style={{ padding: 16 }}>
            <span className="label">ROI Atual</span>
            <pre>{roi ? JSON.stringify(roi, null, 2) : 'Não definida'}</pre>
          </div>
          <div className="card" style={{ padding: 16 }}>
            <span className="label">Linha Atual</span>
            <pre>{line ? JSON.stringify(line, null, 2) : 'Não definida'}</pre>
          </div>
          <div className="card" style={{ padding: 16 }}>
            <span className="label">Direção</span>
            <pre>{direction}</pre>
          </div>
        </div>
      </div>
    </div>
  )
}
