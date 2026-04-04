import { useEffect, useRef, useState } from 'react'

function easeOut(t) {
  return 1 - Math.pow(1 - t, 3)
}

export default function CounterDisplay({ value = 0, label = 'CONTAGEM TOTAL' }) {
  const [displayed, setDisplayed] = useState(value)
  const animRef = useRef(null)
  const fromRef = useRef(value)

  useEffect(() => {
    if (value === fromRef.current) return

    const start = fromRef.current
    const end = value
    const duration = 400
    const startTime = performance.now()

    if (animRef.current) cancelAnimationFrame(animRef.current)

    function tick(now) {
      const elapsed = now - startTime
      const t = Math.min(elapsed / duration, 1)
      const current = Math.round(start + (end - start) * easeOut(t))
      setDisplayed(current)
      if (t < 1) {
        animRef.current = requestAnimationFrame(tick)
      } else {
        fromRef.current = end
      }
    }

    animRef.current = requestAnimationFrame(tick)
    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current)
    }
  }, [value])

  return (
    <div className="counter-card">
      <div className="counter-label">{label}</div>
      <div className="counter-value">
        {displayed.toLocaleString('pt-BR')}
      </div>
    </div>
  )
}
