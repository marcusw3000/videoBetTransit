import { useEffect, useRef } from 'react'

/**
 * Overlay visual do cliente:
 * - ROI (retângulo amarelo)
 * - Linha de contagem (vermelha)
 * - Bounding boxes nos veículos trackados (laranja = ativo, verde = contado)
 * - Anchor point (ponto vermelho)
 * - Track ID + tipo do veículo
 */
export default function VideoOverlayCanvas({ detectionFrame, videoRef }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    if (!detectionFrame || !canvasRef.current || !videoRef?.current) return

    const canvas = canvasRef.current
    const video = videoRef.current
    const ctx = canvas.getContext('2d')

    const displayW = video.clientWidth
    const displayH = video.clientHeight
    canvas.width = displayW
    canvas.height = displayH

    const { frameWidth, frameHeight, roi, countLine, detections, totalCount } = detectionFrame

    if (!frameWidth || !frameHeight) return

    const sx = (x) => (x / frameWidth) * displayW
    const sy = (y) => (y / frameHeight) * displayH

    ctx.clearRect(0, 0, displayW, displayH)

    // ── ROI (retângulo amarelo tracejado) ──
    if (roi) {
      ctx.strokeStyle = 'rgba(255, 255, 0, 0.6)'
      ctx.lineWidth = 2
      ctx.setLineDash([8, 6])
      ctx.strokeRect(sx(roi.x), sy(roi.y), sx(roi.w), sy(roi.h))
      ctx.setLineDash([])
    }

    // ── Linha de contagem (vermelha) ──
    if (countLine) {
      ctx.strokeStyle = 'rgba(255, 40, 40, 0.9)'
      ctx.lineWidth = 3
      ctx.shadowColor = 'rgba(255, 40, 40, 0.5)'
      ctx.shadowBlur = 8
      ctx.beginPath()
      ctx.moveTo(sx(countLine.x1), sy(countLine.y1))
      ctx.lineTo(sx(countLine.x2), sy(countLine.y2))
      ctx.stroke()
      ctx.shadowBlur = 0
    }

    // ── Bounding boxes dos veículos ──
    if (detections) {
      for (const det of detections) {
        const { bbox, center } = det
        const bx = sx(bbox.x)
        const by = sy(bbox.y)
        const bw = sx(bbox.w)
        const bh = sy(bbox.h)

        // Cor: verde se contado, laranja se ativo
        const color = det.counted
          ? 'rgba(50, 220, 100, 0.9)'
          : 'rgba(255, 165, 0, 0.8)'

        // Borda do bbox
        ctx.strokeStyle = color
        ctx.lineWidth = 2
        ctx.strokeRect(bx, by, bw, bh)

        // Label: #ID tipo
        const label = `#${det.trackId} ${det.vehicleType}`
        ctx.font = `bold ${Math.max(11, displayW * 0.014)}px Inter, Arial, sans-serif`
        const textW = ctx.measureText(label).width

        // Fundo da label
        ctx.fillStyle = det.counted
          ? 'rgba(30, 120, 50, 0.85)'
          : 'rgba(140, 80, 0, 0.85)'
        const labelH = Math.max(16, displayW * 0.02)
        ctx.fillRect(bx, by - labelH - 2, textW + 10, labelH + 2)

        // Texto da label
        ctx.fillStyle = '#ffffff'
        ctx.fillText(label, bx + 5, by - 5)

        // Anchor point (ponto vermelho no bottom-center)
        if (center) {
          ctx.beginPath()
          ctx.arc(sx(center.x), sy(center.y), 4, 0, 2 * Math.PI)
          ctx.fillStyle = 'rgba(255, 40, 40, 0.9)'
          ctx.fill()
        }
      }
    }

    // ── Contador total (canto superior esquerdo) ──
    if (totalCount !== undefined) {
      const countText = `TOTAL: ${totalCount}`
      ctx.font = `bold ${Math.max(18, displayW * 0.028)}px Inter, Arial, sans-serif`
      const tw = ctx.measureText(countText).width

      ctx.fillStyle = 'rgba(0, 0, 0, 0.6)'
      ctx.fillRect(10, 10, tw + 20, Math.max(32, displayW * 0.035))

      ctx.fillStyle = '#30ff70'
      ctx.fillText(countText, 20, Math.max(34, displayW * 0.032) + 2)
    }
  }, [detectionFrame, videoRef])

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 3,
      }}
    />
  )
}
