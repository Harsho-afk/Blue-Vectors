import { useEffect, useRef } from 'react'
import { useTheme } from '@/context/theme-provider'

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  opacity: number
}

export function GlobalBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const { resolvedTheme } = useTheme()

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const COUNT = 90
    const MAX_DIST = 150
    const particles: Particle[] = []

    const resize = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
    }
    resize()
    window.addEventListener('resize', resize)

    for (let i = 0; i < COUNT; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        radius: Math.random() * 1.8 + 0.8,
        opacity: Math.random() * 0.5 + 0.3,
      })
    }

    let raf: number

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      for (const p of particles) {
        p.x += p.vx
        p.y += p.vy
        if (p.x < 0 || p.x > canvas.width) p.vx *= -1
        if (p.y < 0 || p.y > canvas.height) p.vy *= -1
      }

      const isDark = resolvedTheme === 'dark'

      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const a = particles[i]
          const b = particles[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < MAX_DIST) {
            const alpha = (1 - dist / MAX_DIST) * 0.28
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(b.x, b.y)
            ctx.strokeStyle = isDark
              ? `rgba(224, 92, 0, ${alpha})`
              : `rgba(249, 115, 22, ${alpha * 0.8})`
            ctx.lineWidth = 0.8
            ctx.stroke()
          }
        }
      }

      for (const p of particles) {
        const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.radius * 6)
        if (isDark) {
          grad.addColorStop(0, `rgba(255, 107, 0, ${p.opacity * 0.45})`)
          grad.addColorStop(1, 'rgba(255, 107, 0, 0)')
        } else {
          grad.addColorStop(0, `rgba(249, 115, 22, ${p.opacity * 0.25})`)
          grad.addColorStop(1, 'rgba(249, 115, 22, 0)')
        }
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.radius * 6, 0, Math.PI * 2)
        ctx.fillStyle = grad
        ctx.fill()

        ctx.beginPath()
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
        ctx.fillStyle = isDark
          ? `rgba(255, 140, 60, ${p.opacity})`
          : `rgba(234, 88, 12, ${p.opacity * 0.9})`
        ctx.fill()
      }

      raf = requestAnimationFrame(draw)
    }

    draw()

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
    }
  }, [resolvedTheme])

  const isDark = resolvedTheme === 'dark'

  return (
    <div
      style={{
        width: '100vw',
        height: '100vh',
        background: isDark
          ? 'radial-gradient(ellipse at 50% 40%, #100600 0%, #050200 60%, #000000 100%)'
          : 'radial-gradient(ellipse at 50% 40%, #FFF4ED 0%, #FFFBF9 60%, #FFFFFF 100%)',
        overflow: 'hidden',
        position: 'fixed',
        inset: 0,
        zIndex: -1,
        pointerEvents: 'none',
      }}
    >
      <canvas
        ref={canvasRef}
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
      />
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: isDark
            ? 'radial-gradient(ellipse at center, transparent 35%, rgba(0,0,0,0.85) 100%)'
            : 'radial-gradient(ellipse at center, transparent 35%, rgba(255,255,255,0.4) 100%)',
          pointerEvents: 'none',
        }}
      />
    </div>
  )
}
