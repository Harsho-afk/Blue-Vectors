import { useCallback, useRef, useState } from 'react'
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  ChevronDown,
  Globe,
  HardDrive,
  Loader2,
  MinusCircle,
  Phone,
  Play,
  Search,
  Shield,
  Sparkles,
  Zap,
} from 'lucide-react'
import { API } from '@/lib/aria-api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'

// ── Types ───────────────────────────────────────────────────────────────────

interface StepEvent {
  step: string
  status: 'running' | 'done' | 'error' | 'skipped'
  seed?: string
  platform?: string
  username?: string
  message?: string
  found?: number
  posts?: number
  breaches?: number
  pairs?: number
  count?: number
  claims?: number
  results?: number
  entities?: number
  accounts_collected?: number
  display_name?: string
  error?: string
  total_seeds?: number
  usernames?: number
  emails?: number
  phones?: number
}

type Phase = 'discovery' | 'collection' | 'breach' | 'phone' | 'dorking' | 'correlation' | 'insights' | 'intelligence'

interface StepEntry {
  id: string
  phase: Phase
  label: string
  status: 'pending' | 'running' | 'done' | 'error' | 'skipped'
  detail?: string
  error?: string
}

interface Props {
  caseId: string
  hasIdentifiers: boolean
  onComplete: () => void
}

// ── Phase metadata ──────────────────────────────────────────────────────────

const PHASE_META: Record<Phase, { label: string; icon: React.ElementType }> = {
  discovery: { label: 'Platform Discovery', icon: Globe },
  collection: { label: 'Deep Collection', icon: HardDrive },
  breach: { label: 'Breach Analysis', icon: Shield },
  phone: { label: 'Phone Lookup', icon: Phone },
  dorking: { label: 'Web Expansion Survey', icon: Globe },
  correlation: { label: 'Identity Correlation', icon: Zap },
  insights: { label: 'Insight Analysis', icon: Sparkles },
  intelligence: { label: 'Intelligence Briefing', icon: Bot },
}

const PHASE_ORDER: Phase[] = ['discovery', 'collection', 'breach', 'phone', 'dorking', 'correlation', 'insights', 'intelligence']

// ── Helpers ─────────────────────────────────────────────────────────────────

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function stepKey(event: StepEvent): string {
  const { step, seed, platform, username } = event
  if (step === 'collect') return `collect-${platform}-${username || seed}`
  if (step === 'maigret') return `maigret-${seed}`
  if (step === 'breach') return `breach-${seed}`
  if (step === 'phone') return `phone-${seed}`
  return step
}

function stepToPhase(step: string): Phase {
  if (step === 'maigret') return 'discovery'
  if (step === 'collect') return 'collection'
  if (step === 'breach') return 'breach'
  if (step === 'phone') return 'phone'
  if (step === 'dorking') return 'dorking'
  if (step === 'correlate') return 'correlation'
  if (step === 'insights') return 'insights'
  if (step === 'intelligence') return 'intelligence'
  return 'discovery'
}

function stepLabel(event: StepEvent): string {
  const { step, seed, platform, username } = event
  if (step === 'maigret') return `Search platforms for "${seed}"`
  if (step === 'collect') return `Collect ${capitalize(platform || '?')} — ${username || seed}`
  if (step === 'breach') return `Check breaches for ${seed}`
  if (step === 'phone') return `Lookup phone ${seed}`
  if (step === 'dorking') return 'Web expansion survey (dorking)'
  if (step === 'correlate') return 'Run identity correlation'
  if (step === 'insights') return 'Compute insights'
  if (step === 'intelligence') return 'Generate intelligence briefing'
  return step
}

function stepDetail(event: StepEvent): string | undefined {
  if (event.step === 'maigret' && event.status === 'done') return `Found on ${event.found ?? 0} platforms`
  if (event.step === 'collect' && event.status === 'done') return `${event.posts ?? 0} posts collected`
  if (event.step === 'breach' && event.status === 'done') return `${event.breaches ?? 0} breach(es) found`
  if (event.step === 'correlate' && event.status === 'done') return `${event.pairs ?? 0} pair(s) analyzed`
  if (event.step === 'insights' && event.status === 'done') return `${event.count ?? 0} insight(s) generated`
  if (event.step === 'dorking' && event.status === 'done') return `${event.results ?? 0} results, ${event.entities ?? 0} entities`
  if (event.step === 'intelligence' && event.status === 'done') return `${event.claims ?? 0} cited claim(s)`
  return event.message
}

// ── Status indicator ────────────────────────────────────────────────────────

function StatusIcon({ status }: { status: StepEntry['status'] }) {
  switch (status) {
    case 'running':
      return <Loader2 className='h-4 w-4 animate-spin text-primary' />
    case 'done':
      return <CheckCircle2 className='h-4 w-4 text-green-500' />
    case 'error':
      return <AlertCircle className='h-4 w-4 text-destructive' />
    case 'skipped':
      return <MinusCircle className='h-4 w-4 text-muted-foreground' />
    default:
      return <div className='h-2 w-2 rounded-full bg-muted-foreground/30' />
  }
}

// ── SSE Parser ──────────────────────────────────────────────────────────────

function parseSSEChunk(chunk: string): StepEvent[] {
  const events: StepEvent[] = []
  const lines = chunk.split('\n')
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      try {
        events.push(JSON.parse(line.slice(6)))
      } catch {
        // skip malformed events
      }
    }
  }
  return events
}

// ── Component ───────────────────────────────────────────────────────────────

export function InvestigationRunner({ caseId, hasIdentifiers, onComplete }: Props) {
  const [isRunning, setIsRunning] = useState(false)
  const [isDone, setIsDone] = useState(false)
  const [steps, setSteps] = useState<StepEntry[]>([])
  const [summary, setSummary] = useState<string | null>(null)
  const [globalError, setGlobalError] = useState<string | null>(null)
  const [expandedPhases, setExpandedPhases] = useState<Set<Phase>>(new Set(PHASE_ORDER))
  const abortRef = useRef<AbortController | null>(null)

  const handleEvent = useCallback((event: StepEvent) => {
    if (event.step === 'init') return
    if (event.step === 'complete') {
      setSummary(
        `Investigation complete — ${event.accounts_collected ?? 0} account(s) collected`
      )
      return
    }
    if (event.step === 'error') {
      setGlobalError(event.message || event.error || 'Unknown error')
      return
    }

    const id = stepKey(event)
    const phase = stepToPhase(event.step)
    const label = stepLabel(event)
    const detail = stepDetail(event)

    setSteps((prev) => {
      const idx = prev.findIndex((s) => s.id === id)
      const entry: StepEntry = {
        id,
        phase,
        label,
        status: event.status === 'error' ? 'error' : event.status === 'skipped' ? 'skipped' : event.status === 'done' ? 'done' : 'running',
        detail,
        error: event.error,
      }
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = entry
        return next
      }
      return [...prev, entry]
    })
  }, [])

  const runInvestigation = useCallback(async () => {
    setIsRunning(true)
    setIsDone(false)
    setSteps([])
    setSummary(null)
    setGlobalError(null)
    setExpandedPhases(new Set(PHASE_ORDER))

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const response = await fetch(`${API}/api/cases/${caseId}/run`, {
        method: 'POST',
        credentials: 'include',
        signal: controller.signal,
      })

      if (!response.ok) {
        const err = await response.json().then((d) => d.detail).catch(() => response.statusText)
        throw new Error(err)
      }

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''

        for (const part of parts) {
          const events = parseSSEChunk(part)
          for (const event of events) {
            handleEvent(event)
          }
        }
      }

      // Process remaining buffer
      if (buffer.trim()) {
        const events = parseSSEChunk(buffer)
        for (const event of events) {
          handleEvent(event)
        }
      }
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        setGlobalError(e instanceof Error ? e.message : 'Investigation failed')
      }
    } finally {
      setIsRunning(false)
      setIsDone(true)
      abortRef.current = null
      onComplete()
    }
  }, [caseId, handleEvent, onComplete])

  const togglePhase = (phase: Phase) => {
    setExpandedPhases((prev) => {
      const next = new Set(prev)
      if (next.has(phase)) next.delete(phase)
      else next.add(phase)
      return next
    })
  }

  const phaseSteps = (phase: Phase) => steps.filter((s) => s.phase === phase)
  const activePhases = PHASE_ORDER.filter((p) => phaseSteps(p).length > 0)

  const hasAnySteps = steps.length > 0

  // Compact button-only mode when nothing has run yet
  if (!hasAnySteps && !isRunning && !globalError) {
    return (
      <Card>
        <CardContent className='flex items-center justify-between py-4'>
          <div className='flex items-center gap-3'>
            <div className='flex h-9 w-9 items-center justify-center rounded-full bg-primary/10'>
              <Search className='h-4 w-4 text-primary' />
            </div>
            <div>
              <p className='text-sm font-medium'>Run Investigation</p>
              <p className='text-xs text-muted-foreground'>
                Discover platforms, collect data, and correlate identities — all in one click
              </p>
            </div>
          </div>
          <Button
            onClick={runInvestigation}
            disabled={!hasIdentifiers}
            size='sm'
          >
            <Play className='h-4 w-4' />
            Run
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className='pb-3'>
        <div className='flex items-center justify-between'>
          <CardTitle className='flex items-center gap-2 text-base'>
            <Search className='h-4 w-4' />
            Investigation
          </CardTitle>
          <div className='flex items-center gap-2'>
            {isRunning && (
              <Badge variant='default' className='animate-pulse'>
                <Loader2 className='mr-1 h-3 w-3 animate-spin' />
                Running
              </Badge>
            )}
            {isDone && !isRunning && (
              <Badge variant='secondary'>
                <CheckCircle2 className='mr-1 h-3 w-3' />
                Complete
              </Badge>
            )}
            {!isRunning && (
              <Button
                onClick={runInvestigation}
                disabled={!hasIdentifiers}
                size='sm'
                variant={isDone ? 'outline' : 'default'}
              >
                <Play className='h-3 w-3' />
                {isDone ? 'Re-run' : 'Run'}
              </Button>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className='space-y-1 pt-0'>
        {/* Global error */}
        {globalError && (
          <div className='mb-3 flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive'>
            <AlertCircle className='h-4 w-4 shrink-0' />
            {globalError}
          </div>
        )}

        {/* Summary banner */}
        {summary && !isRunning && (
          <div className='mb-3 flex items-center gap-2 rounded-lg border border-green-500/30 bg-green-500/10 px-3 py-2 text-sm text-green-700 dark:text-green-400'>
            <CheckCircle2 className='h-4 w-4 shrink-0' />
            {summary}
          </div>
        )}

        {/* Phase groups */}
        {activePhases.map((phase) => {
          const meta = PHASE_META[phase]
          const pSteps = phaseSteps(phase)
          const Icon = meta.icon
          const isExpanded = expandedPhases.has(phase)
          const doneCount = pSteps.filter((s) => s.status === 'done').length
          const errorCount = pSteps.filter((s) => s.status === 'error').length
          const runningCount = pSteps.filter((s) => s.status === 'running').length

          return (
            <Collapsible key={phase} open={isExpanded} onOpenChange={() => togglePhase(phase)}>
              <CollapsibleTrigger className='flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-muted/50'>
                <Icon className='h-3.5 w-3.5 text-muted-foreground' />
                <span className='flex-1 text-sm font-medium'>{meta.label}</span>
                <div className='flex items-center gap-1.5'>
                  {runningCount > 0 && (
                    <Loader2 className='h-3 w-3 animate-spin text-primary' />
                  )}
                  {doneCount > 0 && (
                    <Badge variant='secondary' className='h-5 px-1.5 text-xs'>
                      {doneCount}/{pSteps.length}
                    </Badge>
                  )}
                  {errorCount > 0 && (
                    <Badge variant='destructive' className='h-5 px-1.5 text-xs'>
                      {errorCount} failed
                    </Badge>
                  )}
                  <ChevronDown
                    className={cn(
                      'h-3.5 w-3.5 text-muted-foreground transition-transform',
                      !isExpanded && '-rotate-90'
                    )}
                  />
                </div>
              </CollapsibleTrigger>

              <CollapsibleContent>
                <div className='ml-5 border-l pl-3'>
                  {pSteps.map((entry) => (
                    <div
                      key={entry.id}
                      className='flex items-start gap-2 py-1.5'
                    >
                      <div className='mt-0.5'>
                        <StatusIcon status={entry.status} />
                      </div>
                      <div className='min-w-0 flex-1'>
                        <p className={cn(
                          'text-sm',
                          entry.status === 'error' && 'text-destructive',
                          entry.status === 'skipped' && 'text-muted-foreground',
                        )}>
                          {entry.label}
                        </p>
                        {entry.detail && entry.status !== 'running' && (
                          <p className='text-xs text-muted-foreground'>
                            {entry.detail}
                          </p>
                        )}
                        {entry.status === 'running' && entry.detail && (
                          <p className='text-xs text-primary'>
                            {entry.detail}
                          </p>
                        )}
                        {entry.error && (
                          <p className='text-xs text-destructive'>
                            {entry.error}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </CollapsibleContent>
            </Collapsible>
          )
        })}
      </CardContent>
    </Card>
  )
}
