import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Clock,
  ExternalLink,
  Eye,
  GitBranch,
  Globe,
  Info,
  MessageSquare,
  Search,
  Shield,
  Zap,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'

// ── Types ──

interface TimelineEvent {
  id: string
  timestamp: string | null
  event_type: string
  platform: string | null
  account_id: number | null
  account_label: string | null
  title: string
  description: string | null
  confidence?: string
  spike?: boolean
  metadata?: Record<string, unknown> | null
}

interface TimelineAccount {
  id: number
  platform: string
  username: string
  display_name: string | null
  avatar: string | null
}

interface TimelineData {
  events: TimelineEvent[]
  accounts: TimelineAccount[]
  time_range: {
    earliest: string | null
    latest: string | null
    total_events: number
  }
}

interface TimelineViewProps {
  caseId: string
  apiBase: string
}

// ── Constants ──

// Distinct colors for different accounts (not platform-based)
const ACCOUNT_PALETTE = [
  '#3B82F6', // blue
  '#F97316', // orange
  '#10B981', // emerald
  '#EC4899', // pink
  '#8B5CF6', // purple
  '#EAB308', // yellow
  '#06B6D4', // cyan
  '#EF4444', // red
  '#14B8A6', // teal
  '#A855F7', // violet
]

const SYSTEM_COLOR = '#6B7280'

const EVENT_ICONS: Record<string, typeof Calendar> = {
  account_created: Calendar,
  post: MessageSquare,
  comment: MessageSquare,
  repo: GitBranch,
  push: GitBranch,
  network: Globe,
  osint_lookup: Search,
  breach: Shield,
  correlation: Zap,
  insight: Eye,
  report: Info,
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// ── Helpers ──

function formatDate(iso: string) {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatTime(iso: string) {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
}

function dateKey(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function getPostUrl(event: TimelineEvent): string | null {
  if (!event.metadata) return null
  const url = event.metadata.url as string | undefined
  if (url && typeof url === 'string' && url.startsWith('http')) return url

  // Construct URLs from known platforms + metadata
  const platform = event.platform
  if (platform === 'reddit') {
    const sub = event.metadata.subreddit as string | undefined
    if (sub) return `https://reddit.com/r/${sub}`
  }
  if (platform === 'github') {
    const repo = event.metadata.repo as string | undefined
    if (repo) return `https://github.com/${repo}`
  }
  return null
}

// ── Component ──

export function TimelineView({ caseId, apiBase }: TimelineViewProps) {
  const [data, setData] = useState<TimelineData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedDay, setSelectedDay] = useState<string | null>(null)
  const [platformFilter, setPlatformFilter] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    setLoading(true)
    fetch(`${apiBase}/api/cases/${caseId}/timeline`, { credentials: 'include' })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((d: TimelineData) => {
        setData(d)
        setError(null)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [caseId, apiBase])

  // Assign unique colors per account_label
  const accountColorMap = useMemo(() => {
    if (!data) return new Map<string, string>()
    const map = new Map<string, string>()
    data.accounts.forEach((a, i) => {
      const label = `${a.platform}:${a.username}`
      map.set(label, ACCOUNT_PALETTE[i % ACCOUNT_PALETTE.length])
    })
    return map
  }, [data])

  const filteredEvents = useMemo(() => {
    if (!data) return []
    return data.events.filter((e) => {
      if (platformFilter && e.account_label !== platformFilter) return false
      if (searchQuery) {
        const q = searchQuery.toLowerCase()
        const match =
          e.title.toLowerCase().includes(q) ||
          (e.description || '').toLowerCase().includes(q) ||
          (e.account_label || '').toLowerCase().includes(q)
        if (!match) return false
      }
      return true
    })
  }, [data, platformFilter, searchQuery])

  const dayEvents = useMemo(() => {
    if (!selectedDay) return []
    return filteredEvents.filter((e) => {
      if (!e.timestamp) return false
      return dateKey(new Date(e.timestamp)) === selectedDay
    })
  }, [filteredEvents, selectedDay])

  if (loading) {
    return (
      <Card>
        <CardContent className='flex items-center justify-center py-20'>
          <div className='flex flex-col items-center gap-3'>
            <div className='h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent' />
            <p className='text-sm text-muted-foreground'>Building timeline…</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className='flex items-center justify-center py-20'>
          <div className='flex flex-col items-center gap-3 text-destructive'>
            <AlertTriangle className='h-8 w-8' />
            <p className='text-sm'>Failed to load timeline: {error}</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!data || data.events.length === 0) {
    return (
      <Card>
        <CardContent className='flex items-center justify-center py-20'>
          <div className='flex flex-col items-center gap-3 text-muted-foreground'>
            <Clock className='h-8 w-8' />
            <p className='text-sm'>No timeline data yet. Run an investigation first.</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className='flex flex-col gap-4'>
      {/* ── Stats + Account filters ── */}
      <div className='flex flex-wrap items-center gap-2'>
        <Badge variant='outline' className='gap-1'>
          <Clock className='h-3 w-3' />
          {data.time_range.total_events} events
        </Badge>
        {data.time_range.earliest && (
          <Badge variant='outline' className='gap-1 text-[10px]'>
            {formatDate(data.time_range.earliest)} → {formatDate(data.time_range.latest!)}
          </Badge>
        )}
        {data.accounts.map((a) => {
          const label = `${a.platform}:${a.username}`
          const color = accountColorMap.get(label) || SYSTEM_COLOR
          const active = platformFilter === label
          return (
            <Badge
              key={a.id}
              variant='outline'
              className='cursor-pointer gap-1'
              style={{
                borderColor: active ? color : undefined,
                backgroundColor: active ? color + '15' : undefined,
              }}
              onClick={() => setPlatformFilter(active ? null : label)}
            >
              <span className='h-2 w-2 rounded-full' style={{ backgroundColor: color }} />
              {a.username}
              <span className='text-[9px] text-muted-foreground'>({a.platform})</span>
            </Badge>
          )
        })}
      </div>

      {/* ── Search ── */}
      <div className='relative'>
        <Search className='absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground' />
        <Input
          placeholder='Search events…'
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className='h-8 pl-7 text-xs'
        />
      </div>

      {/* ── Activity Chart ── */}
      <ActivityChart
        events={filteredEvents}
        accountColorMap={accountColorMap}
        onDaySelect={(day) => setSelectedDay(day)}
        selectedDay={selectedDay}
      />

      {/* ── Day Detail ── */}
      {selectedDay && dayEvents.length > 0 && (
        <DayDetail
          day={selectedDay}
          events={dayEvents}
          accountColorMap={accountColorMap}
          onClose={() => setSelectedDay(null)}
        />
      )}
    </div>
  )
}

// ── Activity Chart (XY Axis, canvas-rendered, colored by account) ──

function ActivityChart({
  events,
  accountColorMap,
  onDaySelect,
  selectedDay,
}: {
  events: TimelineEvent[]
  accountColorMap: Map<string, string>
  onDaySelect: (day: string) => void
  selectedDay: string | null
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [hoveredBar, setHoveredBar] = useState<{
    day: string
    count: number
    x: number
    y: number
    breakdown: Record<string, number>
  } | null>(null)
  const [canvasWidth, setCanvasWidth] = useState(800)
  const canvasHeight = 300

  const years = useMemo(() => {
    const ys = new Set<number>()
    for (const e of events) {
      if (e.timestamp) {
        const y = new Date(e.timestamp).getFullYear()
        if (!isNaN(y) && y > 1970) ys.add(y)
      }
    }
    return [...ys].sort((a, b) => b - a)
  }, [events])

  const [selectedYear, setSelectedYear] = useState(() => years[0] || new Date().getFullYear())

  // Count events per day, per account_label per day, per event_type per day
  const { dayCounts, accountDayCounts, dayTypeCounts, maxCount, accountLabels } = useMemo(() => {
    const counts: Record<string, number> = {}
    const acctCounts: Record<string, Record<string, number>> = {}
    const typeCounts: Record<string, Record<string, number>> = {}
    const labels = new Set<string>()

    for (const e of events) {
      if (!e.timestamp) continue
      const d = new Date(e.timestamp)
      if (isNaN(d.getTime()) || d.getFullYear() !== selectedYear) continue
      const key = dateKey(d)
      counts[key] = (counts[key] || 0) + 1

      const acctLabel = e.account_label || '_system'
      labels.add(acctLabel)
      if (!acctCounts[key]) acctCounts[key] = {}
      acctCounts[key][acctLabel] = (acctCounts[key][acctLabel] || 0) + 1

      if (!typeCounts[key]) typeCounts[key] = {}
      typeCounts[key][e.event_type] = (typeCounts[key][e.event_type] || 0) + 1
    }

    let mx = 0
    for (const v of Object.values(counts)) {
      if (v > mx) mx = v
    }

    return {
      dayCounts: counts,
      accountDayCounts: acctCounts,
      dayTypeCounts: typeCounts,
      maxCount: mx,
      accountLabels: [...labels].sort(),
    }
  }, [events, selectedYear])

  // Resize
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setCanvasWidth(Math.max(entry.contentRect.width, 400))
      }
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  // All dates for selected year
  const allDays = useMemo(() => {
    const days: string[] = []
    const now = new Date()
    const yearEnd = selectedYear < now.getFullYear()
      ? new Date(selectedYear, 11, 31)
      : now
    const current = new Date(selectedYear, 0, 1)
    while (current <= yearEnd) {
      days.push(dateKey(current))
      current.setDate(current.getDate() + 1)
    }
    return days
  }, [selectedYear])

  // Draw chart
  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    canvas.width = canvasWidth * dpr
    canvas.height = canvasHeight * dpr
    ctx.scale(dpr, dpr)
    canvas.style.width = `${canvasWidth}px`
    canvas.style.height = `${canvasHeight}px`

    ctx.clearRect(0, 0, canvasWidth, canvasHeight)

    const padLeft = 50
    const padRight = 20
    const padTop = 20
    const padBottom = 45
    const chartW = canvasWidth - padLeft - padRight
    const chartH = canvasHeight - padTop - padBottom

    if (allDays.length === 0 || maxCount === 0) {
      ctx.fillStyle = '#6B7280'
      ctx.font = '13px Inter, sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('No activity data for this year', canvasWidth / 2, canvasHeight / 2)
      return
    }

    // Background subtle gradient
    const bgGrad = ctx.createLinearGradient(0, padTop, 0, padTop + chartH)
    bgGrad.addColorStop(0, 'rgba(255,255,255,0.02)')
    bgGrad.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = bgGrad
    ctx.fillRect(padLeft, padTop, chartW, chartH)

    // Y axis gridlines + labels
    const yTicks = Math.min(maxCount, 5)
    const yStep = Math.ceil(maxCount / yTicks)
    ctx.fillStyle = '#9CA3AF'
    ctx.font = '11px Inter, sans-serif'
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'

    for (let i = 0; i <= yTicks; i++) {
      const val = i * yStep
      if (val > maxCount && i > 0) break
      const y = padTop + chartH - (val / maxCount) * chartH
      // Gridline
      ctx.strokeStyle = 'rgba(255,255,255,0.06)'
      ctx.lineWidth = 0.5
      ctx.beginPath()
      ctx.moveTo(padLeft, y)
      ctx.lineTo(padLeft + chartW, y)
      ctx.stroke()
      // Label
      ctx.fillStyle = '#9CA3AF'
      ctx.fillText(String(val), padLeft - 8, y)
    }

    // X axis month labels
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.font = '11px Inter, sans-serif'
    let lastMonth = -1
    for (let i = 0; i < allDays.length; i++) {
      const month = parseInt(allDays[i].split('-')[1], 10) - 1
      if (month !== lastMonth) {
        lastMonth = month
        const x = padLeft + (i / allDays.length) * chartW
        ctx.fillStyle = '#9CA3AF'
        ctx.fillText(MONTHS[month], x + 10, padTop + chartH + 10)
        // Faint month divider
        ctx.strokeStyle = 'rgba(255,255,255,0.05)'
        ctx.lineWidth = 0.5
        ctx.beginPath()
        ctx.moveTo(x, padTop)
        ctx.lineTo(x, padTop + chartH)
        ctx.stroke()
      }
    }

    // Draw bars — stacked by account (not platform)
    const gap = allDays.length > 200 ? 0.3 : allDays.length > 100 ? 0.5 : 1
    const barWidth = Math.max(1.5, (chartW / allDays.length) - gap)

    for (let i = 0; i < allDays.length; i++) {
      const day = allDays[i]
      const count = dayCounts[day] || 0
      if (count === 0) continue

      const x = padLeft + (i / allDays.length) * chartW
      const totalBarH = (count / maxCount) * chartH
      const isSelected = selectedDay === day

      // Stacked segments by account
      const acctCounts = accountDayCounts[day] || {}
      let stackY = 0
      for (const acctLabel of accountLabels) {
        const ac = acctCounts[acctLabel] || 0
        if (ac === 0) continue
        const segH = (ac / maxCount) * chartH
        const color = accountColorMap.get(acctLabel) || SYSTEM_COLOR

        ctx.globalAlpha = isSelected ? 1 : 0.8
        ctx.fillStyle = color

        // Rounded top for the topmost segment
        const yPos = padTop + chartH - stackY - segH
        if (barWidth >= 3) {
          const radius = Math.min(2, barWidth / 2)
          ctx.beginPath()
          ctx.moveTo(x, yPos + segH)
          ctx.lineTo(x, yPos + radius)
          ctx.arcTo(x, yPos, x + radius, yPos, stackY === 0 ? 0 : radius)
          ctx.lineTo(x + barWidth - radius, yPos)
          ctx.arcTo(x + barWidth, yPos, x + barWidth, yPos + radius, stackY === 0 ? 0 : radius)
          ctx.lineTo(x + barWidth, yPos + segH)
          ctx.closePath()
          ctx.fill()
        } else {
          ctx.fillRect(x, yPos, barWidth, segH)
        }
        stackY += segH
      }
      ctx.globalAlpha = 1

      // Selected highlight glow
      if (isSelected) {
        ctx.strokeStyle = '#ffffff'
        ctx.lineWidth = 1.5
        ctx.strokeRect(x - 1, padTop + chartH - totalBarH - 1, barWidth + 2, totalBarH + 2)
        // Glow
        ctx.shadowColor = '#3B82F6'
        ctx.shadowBlur = 6
        ctx.strokeRect(x - 1, padTop + chartH - totalBarH - 1, barWidth + 2, totalBarH + 2)
        ctx.shadowBlur = 0
      }
    }

    // Axes
    ctx.strokeStyle = 'rgba(255,255,255,0.2)'
    ctx.lineWidth = 1
    // Y axis
    ctx.beginPath()
    ctx.moveTo(padLeft, padTop)
    ctx.lineTo(padLeft, padTop + chartH)
    ctx.stroke()
    // X axis
    ctx.beginPath()
    ctx.moveTo(padLeft, padTop + chartH)
    ctx.lineTo(padLeft + chartW, padTop + chartH)
    ctx.stroke()

    // Y axis title
    ctx.save()
    ctx.fillStyle = '#9CA3AF'
    ctx.font = '11px Inter, sans-serif'
    ctx.textAlign = 'center'
    ctx.translate(14, padTop + chartH / 2)
    ctx.rotate(-Math.PI / 2)
    ctx.fillText('Events', 0, 0)
    ctx.restore()
  }, [canvasWidth, allDays, dayCounts, accountDayCounts, accountLabels, accountColorMap, maxCount, selectedDay])

  useEffect(() => { draw() }, [draw])

  // Mouse interaction
  const handleCanvasMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current
      if (!canvas || allDays.length === 0) return
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left

      const padLeft = 50
      const padRight = 20
      const padTop = 20
      const chartW = canvasWidth - padLeft - padRight
      const chartH = canvasHeight - padTop - 45

      if (mx < padLeft || mx > padLeft + chartW) {
        setHoveredBar(null)
        return
      }

      const dayIdx = Math.floor(((mx - padLeft) / chartW) * allDays.length)
      if (dayIdx < 0 || dayIdx >= allDays.length) {
        setHoveredBar(null)
        return
      }

      const day = allDays[dayIdx]
      const count = dayCounts[day] || 0
      if (count === 0) {
        setHoveredBar(null)
        return
      }

      const barX = padLeft + (dayIdx / allDays.length) * chartW
      const barH = (count / maxCount) * chartH
      setHoveredBar({
        day,
        count,
        x: barX,
        y: padTop + chartH - barH - 10,
        breakdown: dayTypeCounts[day] || {},
      })
    },
    [allDays, dayCounts, dayTypeCounts, maxCount, canvasWidth]
  )

  const handleCanvasClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current
      if (!canvas || allDays.length === 0) return
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left

      const padLeft = 50
      const padRight = 20
      const chartW = canvasWidth - padLeft - padRight

      if (mx < padLeft || mx > padLeft + chartW) return

      const dayIdx = Math.floor(((mx - padLeft) / chartW) * allDays.length)
      if (dayIdx < 0 || dayIdx >= allDays.length) return

      const day = allDays[dayIdx]
      if (dayCounts[day]) {
        onDaySelect(day)
      }
    },
    [allDays, dayCounts, canvasWidth, onDaySelect]
  )

  const totalYearEvents = Object.values(dayCounts).reduce((s, c) => s + c, 0)
  const activeDays = Object.values(dayCounts).filter((c) => c > 0).length

  return (
    <Card>
      <CardHeader className='pb-2'>
        <div className='flex items-center justify-between'>
          <CardTitle className='text-sm font-medium'>
            {totalYearEvents} events across {activeDays} active days in {selectedYear}
          </CardTitle>
          <div className='flex items-center gap-1'>
            <Button
              size='icon'
              variant='ghost'
              className='h-7 w-7'
              onClick={() => setSelectedYear((y) => y - 1)}
              disabled={!years.includes(selectedYear - 1)}
            >
              <ChevronLeft className='h-4 w-4' />
            </Button>
            <span className='min-w-[3.5rem] text-center text-sm font-semibold'>{selectedYear}</span>
            <Button
              size='icon'
              variant='ghost'
              className='h-7 w-7'
              onClick={() => setSelectedYear((y) => y + 1)}
              disabled={selectedYear >= new Date().getFullYear()}
            >
              <ChevronRight className='h-4 w-4' />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div ref={containerRef} className='relative'>
          <canvas
            ref={canvasRef}
            className='w-full cursor-pointer'
            style={{ height: canvasHeight }}
            onMouseMove={handleCanvasMove}
            onMouseLeave={() => setHoveredBar(null)}
            onClick={handleCanvasClick}
          />
          {/* Tooltip */}
          {hoveredBar && (
            <div
              className='pointer-events-none absolute z-20 min-w-[140px] rounded-lg border border-border bg-popover/95 px-3 py-2 text-xs shadow-xl backdrop-blur-sm'
              style={{
                left: Math.min(hoveredBar.x, canvasWidth - 170),
                top: Math.max(hoveredBar.y - 10, 0),
              }}
            >
              <p className='font-semibold'>{formatDate(hoveredBar.day + 'T00:00:00Z')}</p>
              <p className='mt-0.5 text-muted-foreground'>
                {hoveredBar.count} event{hoveredBar.count !== 1 ? 's' : ''}
              </p>
              {Object.keys(hoveredBar.breakdown).length > 0 && (
                <div className='mt-1.5 border-t border-border/50 pt-1.5 space-y-0.5'>
                  {Object.entries(hoveredBar.breakdown)
                    .sort(([, a], [, b]) => b - a)
                    .map(([type, count]) => (
                      <div key={type} className='flex justify-between gap-3'>
                        <span className='text-muted-foreground'>{type.replace(/_/g, ' ')}</span>
                        <span className='font-medium'>{count}</span>
                      </div>
                    ))}
                </div>
              )}
              <p className='mt-1.5 text-[9px] text-muted-foreground/60'>Click to expand</p>
            </div>
          )}
        </div>
        {/* Legend — per account */}
        <div className='mt-3 flex flex-wrap items-center gap-3 text-[11px]'>
          {accountLabels.map((label) => {
            const color = accountColorMap.get(label) || SYSTEM_COLOR
            const parts = label.split(':')
            const displayName = label === '_system' ? 'ARIA System' : parts[1] || label
            const platform = label === '_system' ? '' : parts[0]
            return (
              <span key={label} className='flex items-center gap-1.5'>
                <span
                  className='inline-block h-3 w-3 rounded-sm'
                  style={{ backgroundColor: color }}
                />
                <span className='font-medium'>{displayName}</span>
                {platform && (
                  <span className='text-[9px] text-muted-foreground'>({platform})</span>
                )}
              </span>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

// ── Day Detail Panel ──

function DayDetail({
  day,
  events,
  accountColorMap,
  onClose,
}: {
  day: string
  events: TimelineEvent[]
  accountColorMap: Map<string, string>
  onClose: () => void
}) {
  // Group by event type
  const grouped = useMemo(() => {
    const groups: Record<string, TimelineEvent[]> = {}
    for (const e of events) {
      const key = e.event_type
      if (!groups[key]) groups[key] = []
      groups[key].push(e)
    }
    return groups
  }, [events])

  const typeOrder = ['post', 'comment', 'repo', 'push', 'account_created', 'network', 'osint_lookup', 'breach', 'correlation', 'insight', 'report']
  const sortedTypes = Object.keys(grouped).sort((a, b) => {
    const ia = typeOrder.indexOf(a)
    const ib = typeOrder.indexOf(b)
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
  })

  const typeLabels: Record<string, string> = {
    post: 'Posts & Reels',
    comment: 'Comments',
    repo: 'Repositories',
    push: 'Code Pushes',
    account_created: 'Account Created',
    osint_lookup: 'OSINT Lookups',
    breach: 'Breaches',
    correlation: 'Correlations',
    insight: 'Insights',
    report: 'Reports',
  }

  return (
    <Card>
      <CardHeader className='pb-3'>
        <div className='flex items-center justify-between'>
          <div>
            <CardTitle className='text-base font-semibold'>
              {formatDate(day + 'T00:00:00Z')}
            </CardTitle>
            <p className='mt-0.5 text-xs text-muted-foreground'>
              {events.length} event{events.length !== 1 ? 's' : ''} on this day
            </p>
          </div>
          <Button size='icon' variant='ghost' className='h-7 w-7' onClick={onClose}>
            <span className='text-sm'>✕</span>
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {/* Summary pills */}
        <div className='mb-4 flex flex-wrap gap-2'>
          {sortedTypes.map((type) => {
            const Icon = EVENT_ICONS[type] || Info
            return (
              <Badge key={type} variant='secondary' className='gap-1.5 py-1 text-[11px]'>
                <Icon className='h-3.5 w-3.5' />
                {grouped[type].length} {typeLabels[type] || type.replace(/_/g, ' ')}
              </Badge>
            )
          })}
        </div>

        {/* Events grouped by type */}
        <div className='space-y-5'>
          {sortedTypes.map((type) => {
            const Icon = EVENT_ICONS[type] || Info
            return (
              <div key={type}>
                <h4 className='mb-2 flex items-center gap-2 border-b border-border/30 pb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
                  <Icon className='h-3.5 w-3.5' />
                  {typeLabels[type] || type.replace(/_/g, ' ')}
                </h4>
                <div className='space-y-1'>
                  {grouped[type].map((event) => {
                    const acctColor = event.account_label
                      ? accountColorMap.get(event.account_label) || SYSTEM_COLOR
                      : SYSTEM_COLOR
                    const postUrl = getPostUrl(event)

                    return (
                      <div
                        key={event.id}
                        className='group flex items-start gap-3 rounded-lg px-3 py-2 transition-colors hover:bg-muted/40'
                      >
                        {/* Time */}
                        <span className='w-12 shrink-0 pt-0.5 text-[11px] font-mono text-muted-foreground'>
                          {event.timestamp ? formatTime(event.timestamp) : '—'}
                        </span>

                        {/* Colored accent bar */}
                        <div
                          className='mt-1 h-8 w-1 shrink-0 rounded-full'
                          style={{ backgroundColor: acctColor }}
                        />

                        {/* Content */}
                        <div className='min-w-0 flex-1'>
                          <div className='flex items-center gap-2'>
                            <span className='text-sm font-medium'>{event.title}</span>
                            {event.spike && (
                              <Badge variant='outline' className='h-4 border-yellow-500/50 px-1.5 text-[9px] text-yellow-400'>
                                spike
                              </Badge>
                            )}
                          </div>
                          {event.description && (
                            <p className='mt-0.5 text-xs text-muted-foreground line-clamp-2'>
                              {event.description}
                            </p>
                          )}
                          {/* Metadata tags */}
                          {event.metadata && (
                            <div className='mt-1 flex flex-wrap gap-1'>
                              {Object.entries(event.metadata).map(([k, v]) => {
                                if (v == null || v === '' || k === 'url') return null
                                const display = Array.isArray(v) ? v.join(', ') : String(v)
                                if (!display) return null
                                return (
                                  <span key={k} className='inline-flex rounded bg-muted/50 px-1.5 py-0.5 text-[9px] text-muted-foreground'>
                                    {k}: {display.length > 30 ? display.slice(0, 28) + '…' : display}
                                  </span>
                                )
                              })}
                            </div>
                          )}
                        </div>

                        {/* Account badge */}
                        {event.account_label && (
                          <Badge
                            variant='outline'
                            className='shrink-0 text-[10px]'
                            style={{ borderColor: acctColor + '55', color: acctColor }}
                          >
                            {event.account_label.split(':')[1] || event.account_label}
                          </Badge>
                        )}

                        {/* Link to post */}
                        {postUrl && (
                          <a
                            href={postUrl}
                            target='_blank'
                            rel='noopener noreferrer'
                            className='shrink-0 rounded-md p-1.5 text-muted-foreground opacity-0 transition-all hover:bg-muted hover:text-foreground group-hover:opacity-100'
                            title='Open in new tab'
                          >
                            <ExternalLink className='h-3.5 w-3.5' />
                          </a>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
