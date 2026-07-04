import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Clock,
  ExternalLink,
  GitBranch,
  Globe,
  Info,
  MessageSquare,
  Search,
  Shield,
  Eye,
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

const ACCOUNT_PALETTE = [
  '#3B82F6', '#F97316', '#10B981', '#EC4899', '#8B5CF6',
  '#EAB308', '#06B6D4', '#EF4444', '#14B8A6', '#A855F7',
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

      {/* ── Swimlane Timeline ── */}
      <SwimlanTimeline
        events={filteredEvents}
        accounts={data.accounts}
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

// ── Swimlane Timeline ──
// Each account gets its own horizontal row. Activity shown as dots sized by event count.

function SwimlanTimeline({
  events,
  accounts,
  accountColorMap,
  onDaySelect,
  selectedDay,
}: {
  events: TimelineEvent[]
  accounts: TimelineAccount[]
  accountColorMap: Map<string, string>
  onDaySelect: (day: string) => void
  selectedDay: string | null
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [hoveredDot, setHoveredDot] = useState<{
    accountLabel: string
    day: string
    count: number
    types: Record<string, number>
    x: number
    y: number
  } | null>(null)

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

  // Build per-account, per-day data
  const { accountLanes, maxDayCount } = useMemo(() => {
    // Build account labels from accounts prop
    const acctLabels = accounts.map((a) => `${a.platform}:${a.username}`)

    // Count per account per day
    const laneData: Record<string, Record<string, { count: number; types: Record<string, number> }>> = {}
    for (const label of acctLabels) {
      laneData[label] = {}
    }

    let maxC = 0
    for (const e of events) {
      if (!e.timestamp || !e.account_label) continue
      const d = new Date(e.timestamp)
      if (isNaN(d.getTime()) || d.getFullYear() !== selectedYear) continue
      const dk = dateKey(d)
      const label = e.account_label
      if (!laneData[label]) laneData[label] = {}
      if (!laneData[label][dk]) laneData[label][dk] = { count: 0, types: {} }
      laneData[label][dk].count++
      laneData[label][dk].types[e.event_type] = (laneData[label][dk].types[e.event_type] || 0) + 1
      if (laneData[label][dk].count > maxC) maxC = laneData[label][dk].count
    }

    return {
      accountLanes: laneData,
      maxDayCount: maxC || 1,
    }
  }, [events, accounts, selectedYear])

  // Build all days for the year
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

  // Compute month markers
  const monthMarkers = useMemo(() => {
    const markers: { month: string; dayIndex: number }[] = []
    let lastMonth = -1
    for (let i = 0; i < allDays.length; i++) {
      const m = parseInt(allDays[i].split('-')[1], 10) - 1
      if (m !== lastMonth) {
        lastMonth = m
        markers.push({ month: MONTHS[m], dayIndex: i })
      }
    }
    return markers
  }, [allDays])

  const accountLabels = Object.keys(accountLanes)
  const totalYearEvents = Object.values(accountLanes).reduce(
    (sum, lane) => sum + Object.values(lane).reduce((s, d) => s + d.count, 0), 0
  )
  const activeDays = new Set(
    Object.values(accountLanes).flatMap((lane) => Object.keys(lane))
  ).size

  const LANE_HEIGHT = 44
  const DOT_MAX_R = 8
  const DOT_MIN_R = 3
  const LABEL_WIDTH = 140

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
        <div ref={containerRef} className='relative overflow-x-auto'>
          {/* Month headers */}
          <div className='flex' style={{ paddingLeft: LABEL_WIDTH }}>
            {monthMarkers.map((m, i) => {
              const nextIdx = i < monthMarkers.length - 1 ? monthMarkers[i + 1].dayIndex : allDays.length
              const span = nextIdx - m.dayIndex
              return (
                <div
                  key={m.month}
                  className='shrink-0 border-l border-border/20 px-1 text-[11px] font-medium text-muted-foreground'
                  style={{ width: span * 4 }}
                >
                  {m.month}
                </div>
              )
            })}
          </div>

          {/* Swimlanes */}
          <div className='mt-1'>
            {accountLabels.map((label) => {
              const color = accountColorMap.get(label) || SYSTEM_COLOR
              const parts = label.split(':')
              const username = parts[1] || label
              const platform = parts[0] || ''
              const lane = accountLanes[label]

              return (
                <div
                  key={label}
                  className='flex items-center border-b border-border/10'
                  style={{ height: LANE_HEIGHT }}
                >
                  {/* Account label */}
                  <div
                    className='flex shrink-0 items-center gap-2 pr-3'
                    style={{ width: LABEL_WIDTH }}
                  >
                    <span
                      className='h-3 w-3 shrink-0 rounded-full'
                      style={{ backgroundColor: color }}
                    />
                    <div className='min-w-0'>
                      <p className='truncate text-xs font-medium' style={{ color }}>
                        {username}
                      </p>
                      <p className='truncate text-[9px] text-muted-foreground'>{platform}</p>
                    </div>
                  </div>

                  {/* Dots strip */}
                  <div className='relative flex flex-1 items-center'>
                    <svg
                      width={allDays.length * 4}
                      height={LANE_HEIGHT}
                      className='block'
                    >
                      {/* Month dividers */}
                      {monthMarkers.map((m) => (
                        <line
                          key={m.month}
                          x1={m.dayIndex * 4}
                          y1={0}
                          x2={m.dayIndex * 4}
                          y2={LANE_HEIGHT}
                          stroke='currentColor'
                          className='text-border/10'
                          strokeWidth={0.5}
                        />
                      ))}
                      {/* Activity dots */}
                      {allDays.map((day, i) => {
                        const data = lane[day]
                        if (!data) return null
                        const r = DOT_MIN_R + ((data.count - 1) / (maxDayCount - 1 || 1)) * (DOT_MAX_R - DOT_MIN_R)
                        const isSelected = selectedDay === day
                        return (
                          <circle
                            key={day}
                            cx={i * 4 + 2}
                            cy={LANE_HEIGHT / 2}
                            r={Math.min(r, LANE_HEIGHT / 2 - 2)}
                            fill={color}
                            opacity={isSelected ? 1 : 0.75}
                            stroke={isSelected ? '#fff' : 'none'}
                            strokeWidth={isSelected ? 1.5 : 0}
                            className='cursor-pointer transition-opacity hover:opacity-100'
                            onMouseEnter={(e) => {
                              const rect = (e.target as SVGElement).getBoundingClientRect()
                              const containerRect = containerRef.current?.getBoundingClientRect()
                              setHoveredDot({
                                accountLabel: label,
                                day,
                                count: data.count,
                                types: data.types,
                                x: rect.left - (containerRect?.left || 0) + rect.width / 2,
                                y: rect.top - (containerRect?.top || 0) - 8,
                              })
                            }}
                            onMouseLeave={() => setHoveredDot(null)}
                            onClick={() => onDaySelect(day)}
                          />
                        )
                      })}
                    </svg>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Tooltip */}
          {hoveredDot && (
            <div
              className='pointer-events-none absolute z-20 min-w-[160px] -translate-x-1/2 -translate-y-full rounded-lg border border-border bg-popover/95 px-3 py-2 text-xs shadow-xl backdrop-blur-sm'
              style={{ left: hoveredDot.x, top: hoveredDot.y }}
            >
              <p className='font-semibold'>{formatDate(hoveredDot.day + 'T00:00:00Z')}</p>
              <p className='text-muted-foreground' style={{ color: accountColorMap.get(hoveredDot.accountLabel) }}>
                {hoveredDot.accountLabel.split(':')[1]}
              </p>
              <p className='mt-0.5 font-medium'>
                {hoveredDot.count} event{hoveredDot.count !== 1 ? 's' : ''}
              </p>
              {Object.keys(hoveredDot.types).length > 0 && (
                <div className='mt-1 space-y-0.5 border-t border-border/50 pt-1'>
                  {Object.entries(hoveredDot.types)
                    .sort(([, a], [, b]) => b - a)
                    .map(([type, count]) => (
                      <div key={type} className='flex justify-between gap-3'>
                        <span className='text-muted-foreground'>{type.replace(/_/g, ' ')}</span>
                        <span className='font-medium'>{count}</span>
                      </div>
                    ))}
                </div>
              )}
              <p className='mt-1 text-[9px] text-muted-foreground/60'>Click to expand</p>
            </div>
          )}
        </div>

        {/* Size legend */}
        <div className='mt-3 flex items-center gap-4 text-[11px] text-muted-foreground'>
          <span className='font-medium'>Activity:</span>
          <span className='flex items-center gap-1'>
            <svg width={10} height={10}><circle cx={5} cy={5} r={DOT_MIN_R} fill='#6B7280' /></svg>
            1 event
          </span>
          <span className='flex items-center gap-1'>
            <svg width={18} height={18}><circle cx={9} cy={9} r={(DOT_MIN_R + DOT_MAX_R) / 2} fill='#6B7280' /></svg>
            moderate
          </span>
          <span className='flex items-center gap-1'>
            <svg width={20} height={20}><circle cx={10} cy={10} r={DOT_MAX_R} fill='#6B7280' /></svg>
            peak
          </span>
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
                        <span className='w-12 shrink-0 pt-0.5 text-[11px] font-mono text-muted-foreground'>
                          {event.timestamp ? formatTime(event.timestamp) : '—'}
                        </span>
                        <div
                          className='mt-1 h-8 w-1 shrink-0 rounded-full'
                          style={{ backgroundColor: acctColor }}
                        />
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
                        {event.account_label && (
                          <Badge
                            variant='outline'
                            className='shrink-0 text-[10px]'
                            style={{ borderColor: acctColor + '55', color: acctColor }}
                          >
                            {event.account_label.split(':')[1] || event.account_label}
                          </Badge>
                        )}
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
