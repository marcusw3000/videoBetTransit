import { useEffect, useRef } from 'react'

/**
 * Overlay visual do cliente:
 * - Linha verde de contagem
 * - Quadrados vermelhos nos veículos contabilizados
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

    const { frameWidth, frameHeight, countLine, detections } = detectionFrame

    if (!frameWidth || !frameHeight) return

    const sx = (x) => (x / frameWidth) * displayW
    const sy = (y) => (y / frameHeight) * displayH

    ctx.clearRect(0, 0, displayW, displayH)

    // ── Quadrados vermelhos nos veículos contabilizados ──
    if (detections) {
      for (const det of detections) {
        if (!det.counted) continue

        const { bbox } = det
        const bx = sx(bbox.x)
        const by = sy(bbox.y)
        const bw = sx(bbox.w)
        const bh = sy(bbox.h)

        // Borda vermelha
        ctx.strokeStyle = 'rgba(255, 40, 60, 0.9)'
        ctx.lineWidth = 2.5
        ctx.shadowColor = 'rgba(255, 40, 60, 0.5)'
        ctx.shadowBlur = 6
        ctx.strokeRect(bx, by, bw, bh)
        ctx.shadowBlur = 0
      }
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
