import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  Calendar,
  Clock,
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
import { cn } from '@/lib/utils'

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

// ── Platform colors ──

const PLATFORM_COLORS: Record<string, string> = {
  reddit: '#FF4500',
  twitter: '#1DA1F2',
  github: '#8B5CF6',
  instagram: '#E1306C',
  default: '#6B7280',
}

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

function formatDateTime(iso: string) {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} ${d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })}`
}

// ── Component ──

export function TimelineView({ caseId, apiBase }: TimelineViewProps) {
  const [data, setData] = useState<TimelineData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedEvent, setSelectedEvent] = useState<TimelineEvent | null>(null)
  const [platformFilter, setPlatformFilter] = useState<string | null>(null)
  const [typeFilter, setTypeFilter] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [viewMode, setViewMode] = useState<'lanes' | 'feed'>('lanes')

  // Fetch
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

  // Filtered events
  const filteredEvents = useMemo(() => {
    if (!data) return []
    return data.events.filter((e) => {
      if (platformFilter && e.platform !== platformFilter) return false
      if (typeFilter && e.event_type !== typeFilter) return false
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
  }, [data, platformFilter, typeFilter, searchQuery])

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
      {/* ── Stats ── */}
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
        {data.accounts.map((a) => (
          <Badge
            key={a.id}
            variant='outline'
            className='cursor-pointer gap-1'
            style={{
              borderColor: platformFilter === a.platform
                ? PLATFORM_COLORS[a.platform] || PLATFORM_COLORS.default
                : undefined,
            }}
            onClick={() => setPlatformFilter(platformFilter === a.platform ? null : a.platform)}
          >
            <span
              className='h-2 w-2 rounded-full'
              style={{ backgroundColor: PLATFORM_COLORS[a.platform] || PLATFORM_COLORS.default }}
            />
            {a.username}
          </Badge>
        ))}
      </div>

      {/* ── Controls ── */}
      <div className='flex flex-wrap items-center gap-2'>
        <div className='flex gap-1 rounded-md border border-border p-0.5'>
          <Button
            size='sm'
            variant={viewMode === 'lanes' ? 'secondary' : 'ghost'}
            className='h-7 text-xs'
            onClick={() => setViewMode('lanes')}
          >
            Lanes
          </Button>
          <Button
            size='sm'
            variant={viewMode === 'feed' ? 'secondary' : 'ghost'}
            className='h-7 text-xs'
            onClick={() => setViewMode('feed')}
          >
            Feed
          </Button>
        </div>

        <div className='relative flex-1'>
          <Search className='absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground' />
          <Input
            placeholder='Search events…'
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className='h-8 pl-7 text-xs'
          />
        </div>

        {/* Event type filter */}
        <div className='flex flex-wrap gap-1'>
          {typeFilter && (
            <Badge
              variant='secondary'
              className='cursor-pointer gap-1 text-[10px]'
              onClick={() => setTypeFilter(null)}
            >
              {typeFilter.replace('_', ' ')} ✕
            </Badge>
          )}
        </div>
      </div>

      {/* ── Main View ── */}
      {viewMode === 'lanes' ? (
        <PlatformLanes
          events={filteredEvents}
          accounts={data.accounts}
          onEventClick={setSelectedEvent}
        />
      ) : (
        <EventFeed
          events={filteredEvents}
          onEventClick={setSelectedEvent}
          onTypeFilter={setTypeFilter}
        />
      )}

      {/* ── Event Detail ── */}
      {selectedEvent && (
        <EventDetail event={selectedEvent} onClose={() => setSelectedEvent(null)} />
      )}
    </div>
  )
}

// ── Platform Lanes ──

function PlatformLanes({
  events,
  accounts,
  onEventClick,
}: {
  events: TimelineEvent[]
  accounts: TimelineAccount[]
  onEventClick: (e: TimelineEvent) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)

  // Group events by account
  const lanes = useMemo(() => {
    const byAccount = new Map<string, { account: TimelineAccount | null; events: TimelineEvent[] }>()

    // Initialize lanes for each account
    for (const a of accounts) {
      byAccount.set(`${a.platform}:${a.username}`, { account: a, events: [] })
    }

    // System events lane
    byAccount.set('_system', { account: null, events: [] })

    for (const e of events) {
      if (e.account_label && byAccount.has(e.account_label)) {
        byAccount.get(e.account_label)!.events.push(e)
      } else if (e.account_label) {
        // Try matching
        const key = e.account_label
        if (!byAccount.has(key)) {
          byAccount.set(key, { account: null, events: [] })
        }
        byAccount.get(key)!.events.push(e)
      } else {
        byAccount.get('_system')!.events.push(e)
      }
    }

    // Remove empty lanes
    const result: Array<{ key: string; account: TimelineAccount | null; events: TimelineEvent[] }> = []
    for (const [key, lane] of byAccount) {
      if (lane.events.length > 0) {
        result.push({ key, ...lane })
      }
    }

    return result
  }, [events, accounts])

  // Time range
  const { minTime, rangeMs } = useMemo(() => {
    const timestamps = events
      .map((e) => e.timestamp)
      .filter(Boolean)
      .map((t) => new Date(t!).getTime())
      .filter((t) => !isNaN(t))

    if (timestamps.length === 0) return { minTime: 0, maxTime: 0, rangeMs: 1 }

    const min = Math.min(...timestamps)
    const max = Math.max(...timestamps)
    const range = max - min || 1
    return { minTime: min, maxTime: max, rangeMs: range }
  }, [events])

  // Time axis ticks
  const ticks = useMemo(() => {
    const count = 6
    const result: Array<{ pos: number; label: string }> = []
    for (let i = 0; i <= count; i++) {
      const t = minTime + (rangeMs * i) / count
      const d = new Date(t)
      result.push({
        pos: (i / count) * 100,
        label: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      })
    }
    return result
  }, [minTime, rangeMs])

  function getPosition(timestamp: string | null): number {
    if (!timestamp) return 0
    const t = new Date(timestamp).getTime()
    if (isNaN(t)) return 0
    return ((t - minTime) / rangeMs) * 100
  }

  return (
    <Card>
      <CardHeader className='pb-2'>
        <CardTitle className='text-sm font-medium'>Platform Activity Lanes</CardTitle>
      </CardHeader>
      <CardContent>
        <div className='relative overflow-x-auto' ref={containerRef}>
          {/* Time axis */}
          <div className='relative mb-1 ml-36 h-6 border-b border-border/50'>
            {ticks.map((tick, i) => (
              <div
                key={i}
                className='absolute top-0 flex flex-col items-center'
                style={{ left: `${tick.pos}%` }}
              >
                <span className='text-[9px] text-muted-foreground'>{tick.label}</span>
                <div className='mt-0.5 h-2 w-px bg-border/50' />
              </div>
            ))}
          </div>

          {/* Lanes */}
          <div className='flex flex-col'>
            {lanes.map((lane) => {
              const platform = lane.account?.platform || (lane.key === '_system' ? 'system' : '')
              const color = PLATFORM_COLORS[platform] || PLATFORM_COLORS.default
              const label = lane.account
                ? lane.account.username
                : lane.key === '_system'
                  ? 'ARIA System'
                  : lane.key

              return (
                <div key={lane.key} className='group flex items-center border-b border-border/20 py-2'>
                  {/* Lane label */}
                  <div className='flex w-36 shrink-0 items-center gap-2 pr-3'>
                    <span
                      className='h-3 w-3 shrink-0 rounded-full'
                      style={{ backgroundColor: color }}
                    />
                    <div className='min-w-0'>
                      <p className='truncate text-xs font-medium'>{label}</p>
                      <p className='text-[9px] text-muted-foreground'>
                        {lane.events.length} event{lane.events.length !== 1 ? 's' : ''}
                      </p>
                    </div>
                  </div>

                  {/* Event dots */}
                  <div className='relative h-8 flex-1'>
                    {/* Lane background line */}
                    <div className='absolute left-0 right-0 top-1/2 h-px bg-border/30' />

                    {lane.events.map((event) => {
                      const pos = getPosition(event.timestamp)
                      const isSpike = event.spike
                      const dotSize = isSpike ? 10 : 6

                      return (
                        <button
                          key={event.id}
                          className='absolute -translate-x-1/2 -translate-y-1/2 rounded-full transition-all hover:scale-150 hover:ring-2 hover:ring-white/30'
                          style={{
                            left: `${pos}%`,
                            top: '50%',
                            width: dotSize,
                            height: dotSize,
                            backgroundColor: color,
                            opacity: event.event_type === 'account_created' ? 1 : 0.8,
                            boxShadow: isSpike ? `0 0 6px ${color}` : undefined,
                          }}
                          title={`${event.title}\n${event.timestamp ? formatDateTime(event.timestamp) : ''}`}
                          onClick={() => onEventClick(event)}
                        />
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Legend */}
          <div className='mt-3 flex items-center gap-4 text-[10px] text-muted-foreground'>
            <span>Each dot = one event. Clusters = activity bursts. Gaps = inactivity. Click a dot for details.</span>
            <span className='flex items-center gap-1'>
              <span className='inline-block h-2.5 w-2.5 rounded-full bg-yellow-500 shadow-[0_0_4px_#eab308]' />
              Spike
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Event Feed ──

function EventFeed({
  events,
  onEventClick,
  onTypeFilter,
}: {
  events: TimelineEvent[]
  onEventClick: (e: TimelineEvent) => void
  onTypeFilter: (type: string) => void
}) {
  const [showCount, setShowCount] = useState(50)
  const visible = events.slice(0, showCount)

  // Group by date
  const grouped = useMemo(() => {
    const groups: Array<{ date: string; events: TimelineEvent[] }> = []
    let currentDate = ''

    for (const e of visible) {
      const date = e.timestamp ? formatDate(e.timestamp) : 'Unknown'
      if (date !== currentDate) {
        currentDate = date
        groups.push({ date, events: [] })
      }
      groups[groups.length - 1].events.push(e)
    }
    return groups
  }, [visible])

  return (
    <Card>
      <CardHeader className='pb-2'>
        <CardTitle className='text-sm font-medium'>
          Activity Feed ({events.length} events)
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className='space-y-4'>
          {grouped.map((group) => (
            <div key={group.date}>
              <div className='sticky top-0 z-10 mb-2 bg-card/80 py-1 backdrop-blur-sm'>
                <span className='text-xs font-medium text-muted-foreground'>{group.date}</span>
              </div>
              <div className='space-y-1'>
                {group.events.map((event) => {
                  const Icon = EVENT_ICONS[event.event_type] || Info
                  const color = event.platform
                    ? PLATFORM_COLORS[event.platform] || PLATFORM_COLORS.default
                    : '#6B7280'

                  return (
                    <button
                      key={event.id}
                      className='flex w-full items-start gap-3 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-muted/30'
                      onClick={() => onEventClick(event)}
                    >
                      {/* Time */}
                      <span className='w-12 shrink-0 pt-0.5 text-[10px] text-muted-foreground'>
                        {event.timestamp ? formatTime(event.timestamp) : ''}
                      </span>

                      {/* Icon */}
                      <div
                        className='mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full'
                        style={{ backgroundColor: color + '22', color }}
                      >
                        <Icon className='h-3 w-3' />
                      </div>

                      {/* Content */}
                      <div className='min-w-0 flex-1'>
                        <div className='flex items-center gap-2'>
                          <span className='text-xs font-medium'>{event.title}</span>
                          {event.spike && (
                            <Badge variant='outline' className='h-4 border-yellow-500/50 px-1 text-[9px] text-yellow-400'>
                              spike
                            </Badge>
                          )}
                          {event.confidence && (
                            <Badge
                              variant='outline'
                              className={cn(
                                'h-4 px-1 text-[9px]',
                                event.confidence === 'high' && 'border-green-500/50 text-green-400',
                                event.confidence === 'medium' && 'border-yellow-500/50 text-yellow-400',
                                event.confidence === 'low' && 'border-gray-500/50 text-gray-400'
                              )}
                            >
                              {event.confidence}
                            </Badge>
                          )}
                        </div>
                        {event.description && (
                          <p className='mt-0.5 truncate text-[11px] text-muted-foreground'>
                            {event.description}
                          </p>
                        )}
                      </div>

                      {/* Platform badge */}
                      {event.account_label && (
                        <Badge
                          variant='outline'
                          className='shrink-0 cursor-pointer text-[9px]'
                          style={{ borderColor: color + '44', color }}
                          onClick={(e) => {
                            e.stopPropagation()
                            if (event.platform) onTypeFilter(event.event_type)
                          }}
                        >
                          {event.account_label}
                        </Badge>
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>

        {events.length > showCount && (
          <Button
            variant='ghost'
            size='sm'
            className='mt-4 w-full text-xs'
            onClick={() => setShowCount((c) => c + 50)}
          >
            Load more ({events.length - showCount} remaining)
          </Button>
        )}
      </CardContent>
    </Card>
  )
}

// ── Event Detail Panel ──

function EventDetail({
  event,
  onClose,
}: {
  event: TimelineEvent
  onClose: () => void
}) {
  const Icon = EVENT_ICONS[event.event_type] || Info
  const color = event.platform
    ? PLATFORM_COLORS[event.platform] || PLATFORM_COLORS.default
    : '#6B7280'

  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between pb-3'>
        <div className='flex items-center gap-3'>
          <div
            className='flex h-8 w-8 items-center justify-center rounded-full'
            style={{ backgroundColor: color + '22', color }}
          >
            <Icon className='h-4 w-4' />
          </div>
          <div>
            <CardTitle className='text-sm'>{event.title}</CardTitle>
            <p className='text-[11px] text-muted-foreground'>
              {event.timestamp ? formatDateTime(event.timestamp) : 'No timestamp'}
            </p>
          </div>
        </div>
        <Button size='icon' variant='ghost' className='h-7 w-7' onClick={onClose}>
          <span className='text-xs'>✕</span>
        </Button>
      </CardHeader>
      <CardContent className='grid gap-2 text-sm'>
        {event.account_label && (
          <div className='flex justify-between'>
            <span className='text-muted-foreground'>Account</span>
            <Badge variant='outline' className='text-[10px]' style={{ borderColor: color + '44', color }}>
              {event.account_label}
            </Badge>
          </div>
        )}
        <div className='flex justify-between'>
          <span className='text-muted-foreground'>Event type</span>
          <span className='text-xs'>{event.event_type.replace(/_/g, ' ')}</span>
        </div>
        {event.confidence && (
          <div className='flex justify-between'>
            <span className='text-muted-foreground'>Confidence</span>
            <Badge
              variant='outline'
              className={cn(
                'text-[10px]',
                event.confidence === 'high' && 'border-green-500/50 text-green-400',
                event.confidence === 'medium' && 'border-yellow-500/50 text-yellow-400',
                event.confidence === 'low' && 'border-gray-500/50 text-gray-400'
              )}
            >
              {event.confidence}
            </Badge>
          </div>
        )}
        {event.description && (
          <div className='mt-1'>
            <span className='text-xs text-muted-foreground'>Detail</span>
            <p className='mt-0.5 text-xs'>{event.description}</p>
          </div>
        )}
        {event.metadata && Object.keys(event.metadata).length > 0 && (
          <div className='mt-1'>
            <span className='text-xs text-muted-foreground'>Metadata</span>
            <div className='mt-1 flex flex-wrap gap-1'>
              {Object.entries(event.metadata).map(([k, v]) => {
                if (v == null || v === '') return null
                const display = Array.isArray(v) ? v.join(', ') : String(v)
                return (
                  <Badge key={k} variant='secondary' className='text-[9px]'>
                    {k}: {display.length > 40 ? display.slice(0, 38) + '…' : display}
                  </Badge>
                )
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
