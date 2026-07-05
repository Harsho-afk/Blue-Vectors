import { useCallback, useEffect, useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Bell,
  Check,
  ChevronDown,
  ChevronUp,
  Eye,
  EyeOff,
  Globe,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Zap,
} from 'lucide-react'
import { API } from '@/lib/aria-api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Input } from '@/components/ui/input'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search as SearchBar } from '@/components/search'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { ThemeSwitch } from '@/components/theme-switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

export const Route = createFileRoute('/_authenticated/cases/')({
  component: Cases,
})

interface Case {
  id: number
  investigator_id: number
  title: string
  status: string
  created_at: string
  closed_at: string | null
}

function formatDate(iso: string) {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function padId(id: number) {
  return `CASE-${String(id).padStart(4, '0')}`
}

interface DashboardAlert {
  id: number
  case_id: number
  case_title: string
  title: string
  message: string
  priority: string
  status: string
  created_at: string
  event_type: string | null
  event_source: string | null
  previous_json: Record<string, unknown> | null
  current_json: Record<string, unknown> | null
}

function Cases() {
  const [cases, setCases] = useState<Case[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const navigate = useNavigate()

  useEffect(() => {
    fetch(`${API}/api/cases`, { credentials: 'include' })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((data) => setCases(data.cases || []))
      .catch((e) => setError(e.message))
      .finally(() => setIsLoading(false))
  }, [])

  const filtered = cases.filter((c) => {
    const matchesSearch = c.title
      .toLowerCase()
      .includes(search.toLowerCase())
    const matchesStatus =
      statusFilter === 'all' || c.status === statusFilter
    return matchesSearch && matchesStatus
  })

  return (
    <>
      <Header>
        <SearchBar className='me-auto' />
        <ThemeSwitch />
        <ConfigDrawer />
        <ProfileDropdown />
      </Header>

      <Main>
        <div className='mb-2 flex items-center justify-between space-y-2'>
          <div>
            <h1 className='text-2xl font-bold tracking-tight'>Cases</h1>
            <p className='text-muted-foreground'>
              All investigations in your workspace
            </p>
          </div>
          <Button onClick={() => navigate({ to: '/investigate' })}>
            <Plus />
            New Investigation
          </Button>
        </div>

        {error && (
          <div className='mb-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive'>
            Failed to load cases: {error}
          </div>
        )}

        {/* Monitoring Alerts Widget */}
        <DashboardAlerts />

        {/* Toolbar */}
        <div className='mt-4 flex items-center gap-3'>
          <div className='relative flex-1'>
            <Search className='absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground' />
            <Input
              placeholder='Search cases...'
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className='pl-8'
            />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className='w-[160px]'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='all'>All Statuses</SelectItem>
              <SelectItem value='open'>Open</SelectItem>
              <SelectItem value='closed'>Closed</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Count */}
        {!isLoading && cases.length > 0 && (
          <p className='mt-3 text-xs text-muted-foreground'>
            Showing {filtered.length} of {cases.length} cases
          </p>
        )}

        {/* Table */}
        <Card className='mt-3'>
          <CardContent className='p-0'>
            {isLoading ? (
              <div className='space-y-3 p-6'>
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className='h-10 w-full' />
                ))}
              </div>
            ) : cases.length === 0 ? (
              <div className='flex flex-col items-center justify-center py-12 text-center'>
                <Search className='mb-4 h-12 w-12 text-muted-foreground/50' />
                <h3 className='text-lg font-medium'>No investigations yet</h3>
                <p className='mt-1 text-sm text-muted-foreground'>
                  Start your first investigation to see it here.
                </p>
                <Button
                  className='mt-4'
                  onClick={() => navigate({ to: '/investigate' })}
                >
                  <Plus />
                  Start your first investigation
                </Button>
              </div>
            ) : filtered.length === 0 ? (
              <div className='flex flex-col items-center justify-center py-12 text-center'>
                <p className='text-sm text-muted-foreground'>
                  No cases match your search.
                </p>
                <Button
                  variant='outline'
                  size='sm'
                  className='mt-3'
                  onClick={() => {
                    setSearch('')
                    setStatusFilter('all')
                  }}
                >
                  Clear filters
                </Button>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Case</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Closed</TableHead>
                    <TableHead className='text-right'>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((c) => (
                    <TableRow
                      key={c.id}
                      className='cursor-pointer'
                      onClick={() =>
                        navigate({
                          to: '/cases/$id',
                          params: { id: String(c.id) },
                        })
                      }
                    >
                      <TableCell>
                        <div className='font-medium'>{c.title}</div>
                        <div className='text-xs text-muted-foreground'>
                          {padId(c.id)}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            c.status === 'open' ? 'default' : 'secondary'
                          }
                        >
                          {c.status}
                        </Badge>
                      </TableCell>
                      <TableCell>{formatDate(c.created_at)}</TableCell>
                      <TableCell>
                        {c.closed_at ? (
                          formatDate(c.closed_at)
                        ) : (
                          <span className='text-muted-foreground'>—</span>
                        )}
                      </TableCell>
                      <TableCell className='text-right'>
                        <Button
                          variant='outline'
                          size='sm'
                          onClick={(e) => {
                            e.stopPropagation()
                            navigate({
                              to: '/cases/$id',
                              params: { id: String(c.id) },
                            })
                          }}
                        >
                          View
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </Main>
    </>
  )
}

// ── Dashboard Monitoring Alerts Widget ──

function DashboardAlerts() {
  const [alerts, setAlerts] = useState<DashboardAlert[]>([])
  const [unread, setUnread] = useState(0)
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const navigate = useNavigate()

  const fetchAlerts = useCallback(() => {
    fetch(`${API}/api/alerts/dashboard?limit=10`, { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : { alerts: [], unread: 0 }))
      .then((data) => {
        setAlerts(data.alerts || [])
        setUnread(data.unread || 0)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchAlerts()
    const interval = setInterval(fetchAlerts, 30_000)
    return () => clearInterval(interval)
  }, [fetchAlerts])

  const markRead = (alertId: number) => {
    fetch(`${API}/api/alerts/${alertId}`, {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'read' }),
    }).then(() => fetchAlerts())
  }

  if (loading) {
    return (
      <Card className='mt-4'>
        <CardContent className='py-6'>
          <div className='flex items-center justify-center gap-2'>
            <Loader2 className='size-4 animate-spin text-muted-foreground' />
            <span className='text-sm text-muted-foreground'>Loading alerts...</span>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (alerts.length === 0) return null

  const priorityDot: Record<string, string> = {
    critical: 'bg-red-500',
    high: 'bg-orange-500',
    normal: 'bg-blue-500',
    low: 'bg-gray-400',
  }

  const eventIcon: Record<string, { icon: typeof Activity; color: string }> = {
    profile_changed: { icon: RefreshCw, color: 'text-blue-500' },
    new_posts: { icon: Activity, color: 'text-green-500' },
    network_changed: { icon: Zap, color: 'text-purple-500' },
    account_discovered: { icon: Plus, color: 'text-orange-500' },
    account_disappeared: { icon: EyeOff, color: 'text-red-500' },
    breach_detected: { icon: AlertTriangle, color: 'text-red-600' },
    correlation_drift: { icon: Zap, color: 'text-yellow-500' },
    new_web_mention: { icon: Globe, color: 'text-cyan-500' },
    hard_link_found: { icon: Check, color: 'text-green-600' },
  }

  return (
    <Card className='mt-4 border-orange-500/20'>
      <CardHeader className='pb-3'>
        <div className='flex items-center justify-between'>
          <CardTitle className='flex items-center gap-2 text-base'>
            <Eye className='size-4 text-orange-500' />
            Monitoring Alerts
            {unread > 0 && (
              <Badge variant='destructive' className='text-xs'>
                {unread} new
              </Badge>
            )}
          </CardTitle>
          <Button
            variant='ghost'
            size='sm'
            className='h-7 text-xs'
            onClick={() => {
              fetch(`${API}/api/alerts/mark-all-read`, {
                method: 'POST',
                credentials: 'include',
              }).then(() => fetchAlerts())
            }}
          >
            Mark all read
          </Button>
        </div>
      </CardHeader>
      <CardContent className='space-y-2 pt-0'>
        {alerts.map((alert) => {
          const evtCfg = eventIcon[alert.event_type || ''] || {
            icon: Bell,
            color: 'text-muted-foreground',
          }
          const Icon = evtCfg.icon
          const hasDiff = alert.previous_json && alert.current_json
          const isExpanded = expandedId === alert.id

          return (
            <div
              key={alert.id}
              className={`rounded-lg border transition-colors ${
                alert.status === 'unread'
                  ? 'border-orange-500/30 bg-orange-500/5'
                  : ''
              }`}
            >
              <div
                className='flex items-start gap-3 p-3 cursor-pointer'
                onClick={() => hasDiff && setExpandedId(isExpanded ? null : alert.id)}
              >
                <span
                  className={`mt-1.5 size-2 shrink-0 rounded-full ${priorityDot[alert.priority] || priorityDot.normal}`}
                />
                <div className={`mt-0.5 ${evtCfg.color}`}>
                  <Icon className='size-4' />
                </div>
                <div className='min-w-0 flex-1'>
                  <p className='text-sm font-medium'>{alert.title}</p>
                  <p className='mt-0.5 text-xs text-muted-foreground'>
                    {alert.message}
                  </p>
                  <div className='mt-1 flex items-center gap-2 text-[11px] text-muted-foreground'>
                    <button
                      className='font-medium text-blue-500 hover:underline'
                      onClick={(e) => {
                        e.stopPropagation()
                        navigate({
                          to: '/cases/$id',
                          params: { id: String(alert.case_id) },
                        })
                      }}
                    >
                      {alert.case_title}
                    </button>
                    <span>·</span>
                    <span>{timeAgo(alert.created_at)}</span>
                    {alert.event_source && (
                      <>
                        <span>·</span>
                        <span>{alert.event_source}</span>
                      </>
                    )}
                  </div>
                </div>
                <div className='flex items-center gap-1'>
                  {alert.status === 'unread' && (
                    <Button
                      variant='ghost'
                      size='icon'
                      className='size-6 shrink-0'
                      onClick={(e) => {
                        e.stopPropagation()
                        markRead(alert.id)
                      }}
                    >
                      <Check className='size-3' />
                    </Button>
                  )}
                  {hasDiff && (
                    <div className='text-muted-foreground'>
                      {isExpanded ? (
                        <ChevronUp className='size-4' />
                      ) : (
                        <ChevronDown className='size-4' />
                      )}
                    </div>
                  )}
                </div>
              </div>

              {isExpanded && hasDiff && (
                <AlertDiffView
                  eventType={alert.event_type || ''}
                  previous={alert.previous_json!}
                  current={alert.current_json!}
                />
              )}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}

function AlertDiffView({
  eventType,
  previous,
  current,
}: {
  eventType: string
  previous: Record<string, unknown>
  current: Record<string, unknown>
}) {
  if (eventType === 'profile_changed') {
    const fields = Object.keys(previous)
    return (
      <div className='border-t bg-muted/30 px-3 pb-3 pt-2'>
        <p className='mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground'>
          Profile Changes
        </p>
        <div className='space-y-2'>
          {fields.map((field) => {
            const prev = previous[field] as
              | { previous?: unknown; current?: unknown }
              | unknown
            const curr = current[field] as
              | { previous?: unknown; current?: unknown }
              | unknown
            const oldVal =
              prev && typeof prev === 'object' && prev !== null && 'previous' in prev
                ? String((prev as Record<string, unknown>).previous ?? '—')
                : String(prev ?? '—')
            const newVal =
              curr && typeof curr === 'object' && curr !== null && 'current' in curr
                ? String((curr as Record<string, unknown>).current ?? '—')
                : String(curr ?? '—')
            return (
              <DashDiffRow
                key={field}
                label={field.replace(/_/g, ' ')}
                oldVal={oldVal}
                newVal={newVal}
              />
            )
          })}
        </div>
      </div>
    )
  }

  if (eventType === 'correlation_drift') {
    return (
      <div className='border-t bg-muted/30 px-3 pb-3 pt-2'>
        <p className='mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground'>
          Correlation Change
        </p>
        <DashDiffRow
          label='Confidence'
          oldVal={`${previous.confidence ?? '—'}%`}
          newVal={`${current.confidence ?? '—'}%`}
        />
      </div>
    )
  }

  if (eventType === 'breach_detected') {
    const newBreaches = (current.new_breaches as string[]) || []
    return (
      <div className='border-t bg-muted/30 px-3 pb-3 pt-2'>
        <p className='mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground'>
          Breach Detection
        </p>
        {newBreaches.length > 0 && (
          <div className='space-y-1'>
            {newBreaches.map((b, i) => (
              <span
                key={i}
                className='mr-1.5 inline-block rounded bg-red-500/10 px-1.5 py-0.5 text-xs text-red-600'
              >
                {b}
              </span>
            ))}
          </div>
        )}
      </div>
    )
  }

  const allKeys = new Set([...Object.keys(previous), ...Object.keys(current)])
  return (
    <div className='border-t bg-muted/30 px-3 pb-3 pt-2'>
      <p className='mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground'>
        Change Details
      </p>
      <div className='space-y-2'>
        {[...allKeys].map((key) => (
          <DashDiffRow
            key={key}
            label={key.replace(/_/g, ' ')}
            oldVal={formatVal(previous[key])}
            newVal={formatVal(current[key])}
          />
        ))}
      </div>
    </div>
  )
}

function DashDiffRow({
  label,
  oldVal,
  newVal,
}: {
  label: string
  oldVal: string
  newVal: string
}) {
  const changed = oldVal !== newVal
  return (
    <div className='flex items-center gap-2 text-xs'>
      <span className='w-24 shrink-0 truncate font-medium capitalize text-muted-foreground'>
        {label}
      </span>
      <span
        className={`truncate rounded px-1.5 py-0.5 ${changed ? 'bg-red-500/10 text-red-600 line-through' : 'text-muted-foreground'}`}
      >
        {oldVal}
      </span>
      {changed && (
        <>
          <ArrowRight className='size-3 shrink-0 text-muted-foreground' />
          <span className='truncate rounded bg-green-500/10 px-1.5 py-0.5 text-green-600'>
            {newVal}
          </span>
        </>
      )}
    </div>
  )
}

function formatVal(val: unknown): string {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  return `${Math.floor(diff / 86_400_000)}d ago`
}
