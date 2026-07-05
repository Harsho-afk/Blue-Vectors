import { useCallback, useEffect, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Bell,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  Eye,
  EyeOff,
  Globe,
  Loader2,
  Pause,
  Play,
  Plus,
  Radio,
  RefreshCw,
  RotateCcw,
  Shield,
  Trash2,
  Zap,
} from 'lucide-react'
import { API } from '@/lib/aria-api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'

// ── Types ──

interface MonitorTarget {
  id: number
  case_id: number
  account_id: number | null
  identifier_id: number | null
  status: string
  reason: string
  permitted_sources: string[]
  interval_seconds: number
  next_check_at: string | null
  last_checked_at: string | null
  expires_at: string | null
  created_at: string | null
  event_count: number
  unread_alerts: number
  account: {
    platform: string
    username: string
    display_name: string | null
    image: string | null
  } | null
  identifier: {
    type: string
    value: string
  } | null
}

interface MonitorEvent {
  id: number
  target_id: number
  event_type: string
  source: string
  title: string
  previous_json: Record<string, unknown> | null
  current_json: Record<string, unknown> | null
  evidence_json: Record<string, unknown> | null
  source_url: string | null
  confidence: string | null
  priority: string
  observed_at: string
}

interface Account {
  id: number
  platform: string
  username: string
  display_name: string | null
  profile_image_url: string | null
}

interface Identifier {
  id: number
  identifier_type: string
  value: string
}

// ── Monitoring Panel Component ──

export function MonitoringPanel({
  caseId,
  accounts,
  identifiers,
}: {
  caseId: string
  accounts: Account[]
  identifiers: Identifier[]
}) {
  const [targets, setTargets] = useState<MonitorTarget[]>([])
  const [loading, setLoading] = useState(true)
  const [showEnroll, setShowEnroll] = useState(false)
  const [selectedTarget, setSelectedTarget] = useState<MonitorTarget | null>(
    null
  )
  const [events, setEvents] = useState<MonitorEvent[]>([])
  const [eventsLoading, setEventsLoading] = useState(false)

  const fetchTargets = useCallback(() => {
    fetch(`${API}/api/cases/${caseId}/monitor-targets`, {
      credentials: 'include',
    })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setTargets(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [caseId])

  useEffect(() => {
    fetchTargets()
  }, [fetchTargets])

  const fetchEvents = useCallback(
    (targetId: number) => {
      setEventsLoading(true)
      fetch(`${API}/api/monitor-targets/${targetId}/events?limit=30`, {
        credentials: 'include',
      })
        .then((r) => (r.ok ? r.json() : { events: [] }))
        .then((data) => setEvents(data.events || []))
        .catch(() => {})
        .finally(() => setEventsLoading(false))
    },
    []
  )

  const triggerCheck = (targetId: number) => {
    fetch(`${API}/api/monitor-targets/${targetId}/check`, {
      method: 'POST',
      credentials: 'include',
    }).then(() => fetchTargets())
  }

  const pauseTarget = (targetId: number) => {
    fetch(`${API}/api/monitor-targets/${targetId}/pause`, {
      method: 'POST',
      credentials: 'include',
    }).then(() => fetchTargets())
  }

  const resumeTarget = (targetId: number) => {
    fetch(`${API}/api/monitor-targets/${targetId}/resume`, {
      method: 'POST',
      credentials: 'include',
    }).then(() => fetchTargets())
  }

  const revokeTarget = (targetId: number) => {
    fetch(`${API}/api/monitor-targets/${targetId}`, {
      method: 'DELETE',
      credentials: 'include',
    }).then(() => {
      fetchTargets()
      setSelectedTarget(null)
    })
  }

  const resetBaseline = (targetId: number) => {
    fetch(`${API}/api/monitor-targets/${targetId}/reset-baseline`, {
      method: 'POST',
      credentials: 'include',
    }).then(() => {
      fetchTargets()
      setSelectedTarget(null)
    })
  }

  if (loading) {
    return (
      <div className='flex items-center justify-center py-12'>
        <Loader2 className='size-5 animate-spin text-muted-foreground' />
      </div>
    )
  }

  return (
    <div className='space-y-4'>
      {/* Header */}
      <div className='flex items-center justify-between'>
        <div>
          <h3 className='text-lg font-semibold'>Active Watchlist</h3>
          <p className='text-sm text-muted-foreground'>
            {targets.filter((t) => t.status === 'active').length} active ·{' '}
            {targets.reduce((sum, t) => sum + t.event_count, 0)} total events
          </p>
        </div>
        <Button onClick={() => setShowEnroll(true)} size='sm'>
          <Plus className='mr-1.5 size-3.5' />
          Monitor
        </Button>
      </div>

      {/* Targets List */}
      {targets.length === 0 ? (
        <Card>
          <CardContent className='py-12 text-center'>
            <Eye className='mx-auto mb-3 size-8 text-muted-foreground/40' />
            <p className='text-sm text-muted-foreground'>
              No profiles under monitoring yet. Click "Monitor" to place an
              account or identifier under active surveillance.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className='grid gap-3'>
          {targets.map((target) => (
            <TargetCard
              key={target.id}
              target={target}
              onSelect={() => {
                setSelectedTarget(target)
                fetchEvents(target.id)
              }}
              onCheck={() => triggerCheck(target.id)}
              onPause={() => pauseTarget(target.id)}
              onResume={() => resumeTarget(target.id)}
              onReset={() => resetBaseline(target.id)}
            />
          ))}
        </div>
      )}

      {/* Enroll Dialog */}
      <EnrollDialog
        open={showEnroll}
        onClose={() => setShowEnroll(false)}
        caseId={caseId}
        accounts={accounts}
        identifiers={identifiers}
        onCreated={() => {
          setShowEnroll(false)
          fetchTargets()
        }}
      />

      {/* Event Detail Dialog */}
      {selectedTarget && (
        <EventsDialog
          target={selectedTarget}
          events={events}
          loading={eventsLoading}
          onClose={() => setSelectedTarget(null)}
          onRevoke={() => revokeTarget(selectedTarget.id)}
          onReset={() => resetBaseline(selectedTarget.id)}
        />
      )}
    </div>
  )
}

// ── Target Card ──

function TargetCard({
  target,
  onSelect,
  onCheck,
  onPause,
  onResume,
  onReset,
}: {
  target: MonitorTarget
  onSelect: () => void
  onCheck: () => void
  onPause: () => void
  onResume: () => void
  onReset: () => void
}) {
  const label = target.account
    ? `${target.account.platform}/${target.account.username}`
    : target.identifier
      ? `${target.identifier.type}: ${target.identifier.value}`
      : 'Unknown'

  const statusColors: Record<string, string> = {
    active: 'bg-green-500/10 text-green-600 dark:text-green-400',
    pending_baseline:
      'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400',
    paused: 'bg-gray-500/10 text-gray-600 dark:text-gray-400',
    degraded: 'bg-red-500/10 text-red-600 dark:text-red-400',
    expired: 'bg-gray-500/10 text-gray-500',
    revoked: 'bg-gray-500/10 text-gray-500',
  }

  return (
    <Card
      className='cursor-pointer transition-colors hover:bg-accent/50'
      onClick={onSelect}
    >
      <CardContent className='flex items-center gap-4 py-3'>
        {/* Status indicator */}
        <div className='relative'>
          <div className='flex size-10 items-center justify-center rounded-full bg-muted'>
            {target.account?.image ? (
              <img
                src={target.account.image}
                alt=''
                className='size-10 rounded-full'
              />
            ) : (
              <Eye className='size-4 text-muted-foreground' />
            )}
          </div>
          {target.status === 'active' && (
            <span className='absolute -bottom-0.5 -right-0.5 size-3 rounded-full border-2 border-background bg-green-500' />
          )}
        </div>

        {/* Info */}
        <div className='min-w-0 flex-1'>
          <div className='flex items-center gap-2'>
            <span className='truncate font-medium'>{label}</span>
            <Badge
              variant='outline'
              className={statusColors[target.status] || ''}
            >
              {target.status.replace('_', ' ')}
            </Badge>
            {target.unread_alerts > 0 && (
              <Badge variant='destructive' className='text-xs'>
                {target.unread_alerts}
              </Badge>
            )}
          </div>
          <div className='mt-0.5 flex items-center gap-3 text-xs text-muted-foreground'>
            <span className='flex items-center gap-1'>
              <Activity className='size-3' />
              {target.event_count} events
            </span>
            {target.last_checked_at && (
              <span className='flex items-center gap-1'>
                <Clock className='size-3' />
                Last: {timeAgo(target.last_checked_at)}
              </span>
            )}
            <span className='flex items-center gap-1'>
              <RefreshCw className='size-3' />
              Every {Math.round(target.interval_seconds / 60)}m
            </span>
          </div>
        </div>

        {/* Actions */}
        <div
          className='flex items-center gap-1'
          onClick={(e) => e.stopPropagation()}
        >
          {target.status === 'active' && (
            <>
              <Button
                size='icon'
                variant='ghost'
                className='size-7'
                onClick={onCheck}
                title='Check now'
              >
                <RefreshCw className='size-3.5' />
              </Button>
              <Button
                size='icon'
                variant='ghost'
                className='size-7'
                onClick={onReset}
                title='Reset baseline'
              >
                <RotateCcw className='size-3.5' />
              </Button>
              <Button
                size='icon'
                variant='ghost'
                className='size-7'
                onClick={onPause}
                title='Pause'
              >
                <Pause className='size-3.5' />
              </Button>
            </>
          )}
          {target.status === 'paused' && (
            <Button
              size='icon'
              variant='ghost'
              className='size-7'
              onClick={onResume}
              title='Resume'
            >
              <Play className='size-3.5' />
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// ── Enroll Dialog ──

function EnrollDialog({
  open,
  onClose,
  caseId,
  accounts,
  identifiers,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  caseId: string
  accounts: Account[]
  identifiers: Identifier[]
  onCreated: () => void
}) {
  const [targetType, setTargetType] = useState<'account' | 'identifier'>(
    'account'
  )
  const [selectedId, setSelectedId] = useState('')
  const [reason, setReason] = useState('')
  const [interval, setInterval] = useState('60')
  const [expiry, setExpiry] = useState('30')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const submit = () => {
    if (!selectedId) {
      setError('Please select a target to monitor')
      return
    }
    if (!reason || reason.trim().length < 3) {
      setError('Please provide a monitoring reason (at least 3 characters)')
      return
    }
    setSubmitting(true)
    setError('')

    const body: Record<string, unknown> = {
      reason: reason.trim(),
      interval_minutes: parseInt(interval),
      expires_in_days: parseInt(expiry),
    }
    if (targetType === 'account') body.account_id = parseInt(selectedId)
    else body.identifier_id = parseInt(selectedId)

    fetch(`${API}/api/cases/${caseId}/monitor-targets`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then((r) => {
        if (!r.ok) return r.json().then((d) => Promise.reject(d))
        return r.json()
      })
      .then(() => {
        onCreated()
        setSelectedId('')
        setReason('')
      })
      .catch((e) => {
        // FastAPI 422 returns { detail: [...array of validation errors] }
        // Other errors return { detail: "string" }
        if (Array.isArray(e?.detail)) {
          const msgs = e.detail.map((err: any) => err.msg || JSON.stringify(err)).join('; ')
          setError(msgs)
        } else {
          setError(e?.detail || 'Failed to create monitor target')
        }
      })
      .finally(() => setSubmitting(false))
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className='max-w-md'>
        <DialogHeader>
          <DialogTitle className='flex items-center gap-2'>
            <Shield className='size-5 text-orange-500' />
            Place Under Monitoring
          </DialogTitle>
          <DialogDescription>
            ARIA will periodically check this target for public changes and
            alert you on significant activity.
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          {/* Target type */}
          <div className='space-y-2'>
            <Label>Monitor</Label>
            <Select
              value={targetType}
              onValueChange={(v) => {
                setTargetType(v as 'account' | 'identifier')
                setSelectedId('')
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='account'>Collected Account</SelectItem>
                <SelectItem value='identifier'>Case Identifier</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Target selection */}
          <div className='space-y-2'>
            <Label>
              {targetType === 'account' ? 'Account' : 'Identifier'}
            </Label>
            <Select value={selectedId} onValueChange={setSelectedId}>
              <SelectTrigger>
                <SelectValue
                  placeholder={`Select ${targetType === 'account' ? 'an account' : 'an identifier'}`}
                />
              </SelectTrigger>
              <SelectContent>
                {targetType === 'account'
                  ? accounts.map((a) => (
                      <SelectItem key={a.id} value={String(a.id)}>
                        {a.platform}/{a.username}
                      </SelectItem>
                    ))
                  : identifiers.map((i) => (
                      <SelectItem key={i.id} value={String(i.id)}>
                        {i.identifier_type}: {i.value}
                      </SelectItem>
                    ))}
              </SelectContent>
            </Select>
          </div>

          {/* Reason */}
          <div className='space-y-2'>
            <Label>Monitoring Reason</Label>
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder='e.g. Track public profile changes relevant to case'
            />
          </div>

          {/* Interval */}
          <div className='grid grid-cols-2 gap-3'>
            <div className='space-y-2'>
              <Label>Check Interval</Label>
              <Select value={interval} onValueChange={setInterval}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='15'>Every 15 min</SelectItem>
                  <SelectItem value='30'>Every 30 min</SelectItem>
                  <SelectItem value='60'>Every 1 hour</SelectItem>
                  <SelectItem value='360'>Every 6 hours</SelectItem>
                  <SelectItem value='1440'>Daily</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className='space-y-2'>
              <Label>Expires In</Label>
              <Select value={expiry} onValueChange={setExpiry}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='7'>7 days</SelectItem>
                  <SelectItem value='14'>14 days</SelectItem>
                  <SelectItem value='30'>30 days</SelectItem>
                  <SelectItem value='60'>60 days</SelectItem>
                  <SelectItem value='90'>90 days</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {error && (
            <p className='text-sm text-destructive'>{error}</p>
          )}
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={submitting}>
            {submitting && <Loader2 className='mr-1.5 size-3.5 animate-spin' />}
            Start Monitoring
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Events Dialog ──

function EventsDialog({
  target,
  events,
  loading,
  onClose,
  onRevoke,
  onReset,
}: {
  target: MonitorTarget
  events: MonitorEvent[]
  loading: boolean
  onClose: () => void
  onRevoke: () => void
  onReset: () => void
}) {
  const label = target.account
    ? `${target.account.platform}/${target.account.username}`
    : target.identifier
      ? `${target.identifier.type}: ${target.identifier.value}`
      : 'Target'

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className='max-h-[80vh] max-w-2xl overflow-y-auto'>
        <DialogHeader>
          <DialogTitle className='flex items-center gap-2'>
            <Radio className='size-4 text-green-500' />
            {label}
          </DialogTitle>
          <DialogDescription>
            Status: {target.status} · Reason: {target.reason}
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-3'>
          {/* Stats */}
          <div className='grid grid-cols-3 gap-3'>
            <MiniStat
              label='Events'
              value={target.event_count}
              icon={Activity}
            />
            <MiniStat
              label='Last Check'
              value={target.last_checked_at ? timeAgo(target.last_checked_at) : 'Never'}
              icon={Clock}
            />
            <MiniStat
              label='Expires'
              value={target.expires_at ? daysUntil(target.expires_at) : '—'}
              icon={AlertTriangle}
            />
          </div>

          <Separator />

          {/* Events Timeline */}
          <div>
            <h4 className='mb-2 text-sm font-medium'>Activity Timeline</h4>
            {loading ? (
              <div className='flex justify-center py-6'>
                <Loader2 className='size-4 animate-spin' />
              </div>
            ) : events.length === 0 ? (
              <p className='py-6 text-center text-sm text-muted-foreground'>
                No events detected yet. Monitoring is active.
              </p>
            ) : (
              <div className='space-y-2'>
                {events.map((evt) => (
                  <EventRow key={evt.id} event={evt} />
                ))}
              </div>
            )}
          </div>
        </div>

        <DialogFooter className='gap-2'>
          <Button
            variant='outline'
            size='sm'
            onClick={onReset}
            title='Clear all snapshots and events, re-capture baseline from current state'
          >
            <RotateCcw className='mr-1.5 size-3.5' />
            Reset Baseline
          </Button>
          <Button
            variant='destructive'
            size='sm'
            onClick={onRevoke}
          >
            <Trash2 className='mr-1.5 size-3.5' />
            Revoke Monitoring
          </Button>
          <Button variant='outline' onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Event Row ──

function EventRow({ event }: { event: MonitorEvent }) {
  const [expanded, setExpanded] = useState(false)
  const hasDiff = event.previous_json && event.current_json

  const typeConfig: Record<string, { icon: typeof Activity; color: string }> = {
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

  const config = typeConfig[event.event_type] || {
    icon: Bell,
    color: 'text-muted-foreground',
  }
  const Icon = config.icon

  const priorityBadge: Record<string, string> = {
    critical: 'bg-red-500/10 text-red-600',
    high: 'bg-orange-500/10 text-orange-600',
    normal: 'bg-gray-500/10 text-gray-600',
    low: 'bg-gray-500/10 text-gray-500',
  }

  return (
    <div className='rounded-lg border'>
      <div
        className={`flex items-start gap-3 p-3 ${hasDiff ? 'cursor-pointer' : ''}`}
        onClick={() => hasDiff && setExpanded(!expanded)}
      >
        <div className={`mt-0.5 ${config.color}`}>
          <Icon className='size-4' />
        </div>
        <div className='min-w-0 flex-1'>
          <div className='flex items-center gap-2'>
            <span className='text-sm font-medium'>{event.title}</span>
            <Badge
              variant='outline'
              className={`text-[10px] ${priorityBadge[event.priority] || ''}`}
            >
              {event.priority}
            </Badge>
          </div>
          <div className='mt-0.5 flex items-center gap-2 text-xs text-muted-foreground'>
            <span>{event.source}</span>
            <span>·</span>
            <span>{timeAgo(event.observed_at)}</span>
            {event.confidence && (
              <>
                <span>·</span>
                <span>Confidence: {event.confidence}</span>
              </>
            )}
          </div>
          {event.source_url && (
            <a
              href={event.source_url}
              target='_blank'
              rel='noopener noreferrer'
              className='mt-1 block truncate text-xs text-blue-500 hover:underline'
              onClick={(e) => e.stopPropagation()}
            >
              {event.source_url}
            </a>
          )}
        </div>
        {hasDiff && (
          <div className='mt-0.5 text-muted-foreground'>
            {expanded ? (
              <ChevronUp className='size-4' />
            ) : (
              <ChevronDown className='size-4' />
            )}
          </div>
        )}
      </div>

      {expanded && hasDiff && (
        <ChangeDiff
          eventType={event.event_type}
          previous={event.previous_json!}
          current={event.current_json!}
        />
      )}
    </div>
  )
}

function ChangeDiff({
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
              prev && typeof prev === 'object' && 'previous' in prev
                ? String(prev.previous ?? '—')
                : String(prev ?? '—')
            const newVal =
              curr && typeof curr === 'object' && 'current' in curr
                ? String(curr.current ?? '—')
                : String(curr ?? '—')
            return (
              <DiffRow
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

  if (eventType === 'network_changed') {
    const allKeys = new Set([...Object.keys(previous), ...Object.keys(current)])
    return (
      <div className='border-t bg-muted/30 px-3 pb-3 pt-2'>
        <p className='mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground'>
          Network Changes
        </p>
        <div className='space-y-2'>
          {[...allKeys].map((key) => (
            <DiffRow
              key={key}
              label={key.replace(/_/g, ' ')}
              oldVal={String(previous[key] ?? '—')}
              newVal={String(current[key] ?? '—')}
            />
          ))}
        </div>
      </div>
    )
  }

  if (eventType === 'new_posts') {
    const oldCount = previous.post_count
    const newCount = current.post_count
    const newIds = (current.new_ids as string[]) || []
    return (
      <div className='border-t bg-muted/30 px-3 pb-3 pt-2'>
        <p className='mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground'>
          New Activity
        </p>
        <DiffRow
          label='Post count'
          oldVal={String(oldCount ?? '—')}
          newVal={String(newCount ?? '—')}
        />
        {newIds.length > 0 && (
          <p className='mt-1.5 text-xs text-muted-foreground'>
            {newIds.length} new post{newIds.length > 1 ? 's' : ''} detected
          </p>
        )}
      </div>
    )
  }

  if (eventType === 'correlation_drift') {
    return (
      <div className='border-t bg-muted/30 px-3 pb-3 pt-2'>
        <p className='mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground'>
          Correlation Change
        </p>
        <DiffRow
          label='Confidence'
          oldVal={`${previous.confidence ?? '—'}%`}
          newVal={`${current.confidence ?? '—'}%`}
        />
        {current.band != null && (
          <p className='mt-1.5 text-xs text-muted-foreground'>
            Band: {String(current.band)}
          </p>
        )}
      </div>
    )
  }

  if (eventType === 'breach_detected') {
    const oldBreaches = (previous.breaches as string[]) || []
    const newBreaches = (current.new_breaches as string[]) || []
    return (
      <div className='border-t bg-muted/30 px-3 pb-3 pt-2'>
        <p className='mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground'>
          Breach Detection
        </p>
        <DiffRow
          label='Known breaches'
          oldVal={String(oldBreaches.length)}
          newVal={String(current.total ?? oldBreaches.length + newBreaches.length)}
        />
        {newBreaches.length > 0 && (
          <div className='mt-2 space-y-1'>
            <p className='text-xs font-medium text-red-600'>
              New breaches found:
            </p>
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
          <DiffRow
            key={key}
            label={key.replace(/_/g, ' ')}
            oldVal={formatDiffValue(previous[key])}
            newVal={formatDiffValue(current[key])}
          />
        ))}
      </div>
    </div>
  )
}

function DiffRow({
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

function formatDiffValue(val: unknown): string {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

// ── Mini Stat ──

function MiniStat({
  label,
  value,
  icon: Icon,
}: {
  label: string
  value: string | number
  icon: typeof Activity
}) {
  return (
    <div className='rounded-lg border p-3'>
      <div className='flex items-center gap-1.5 text-xs text-muted-foreground'>
        <Icon className='size-3' />
        {label}
      </div>
      <div className='mt-1 text-sm font-semibold'>{value}</div>
    </div>
  )
}

// ── Utility ──

function timeAgo(iso: string): string {
  const now = Date.now()
  const then = new Date(iso).getTime()
  const diff = now - then
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  return `${Math.floor(diff / 86_400_000)}d ago`
}

function daysUntil(iso: string): string {
  const diff = new Date(iso).getTime() - Date.now()
  if (diff <= 0) return 'Expired'
  const days = Math.ceil(diff / 86_400_000)
  return `${days}d`
}
