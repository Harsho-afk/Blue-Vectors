import { useState } from 'react'
import {
  Bot,
  ChevronDown,
  FileWarning,
  Loader2,
  Sparkles,
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
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { Insight } from '@/components/evidence-panel'

interface Claim {
  narrative_claim: string
  cited_insight_ids: number[]
}

export interface IntelligenceReport {
  id: number
  narrative: string
  claims: Claim[]
  label: string
  created_at: string
}

interface Props {
  caseId: string
  intelligence: IntelligenceReport | null
  insights: Insight[]
  onGenerated: () => void
}

function CitationMarker({
  ids,
  insights,
}: {
  ids: number[]
  insights: Insight[]
}) {
  const [open, setOpen] = useState(false)
  const cited = insights.filter((i) => ids.includes(i.id))

  if (cited.length === 0) return null

  return (
    <Tooltip open={open} onOpenChange={setOpen}>
      <TooltipTrigger asChild>
        <button
          onClick={() => setOpen(!open)}
          className='ml-1 inline-flex items-center rounded bg-primary/10 px-1 py-0.5 font-mono text-xs text-primary hover:bg-primary/20'
        >
          [{ids.join(', ')}]
        </button>
      </TooltipTrigger>
      <TooltipContent
        side='bottom'
        className='max-w-sm bg-card text-card-foreground shadow-lg'
      >
        <div className='space-y-1.5 p-1'>
          {cited.map((ins) => (
            <div key={ins.id} className='text-xs'>
              <span className='font-medium text-primary'>#{ins.id}</span>{' '}
              <Badge variant='outline' className='text-[10px]'>
                {ins.category}
              </Badge>{' '}
              <span className='text-muted-foreground'>{ins.claim}</span>
            </div>
          ))}
        </div>
      </TooltipContent>
    </Tooltip>
  )
}

export function IntelligenceBriefing({
  caseId,
  intelligence,
  insights,
  onGenerated,
}: Props) {
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedClaims, setExpandedClaims] = useState(true)

  const handleGenerate = async () => {
    setGenerating(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/cases/${caseId}/intelligence`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!res.ok) {
        const err = await res
          .json()
          .then((d) => d.detail)
          .catch(() => res.statusText)
        throw new Error(err)
      }
      onGenerated()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }

  if (!intelligence && !generating) {
    return (
      <Card>
        <CardContent className='py-12 text-center'>
          <Bot className='mx-auto mb-2 h-8 w-8 text-muted-foreground' />
          <p className='mb-3 text-sm text-muted-foreground'>
            No executive briefing yet.
          </p>
          {error && (
            <div className='mx-auto mb-3 max-w-md rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive'>
              {error}
            </div>
          )}
          <Button
            onClick={handleGenerate}
            disabled={insights.length === 0}
            size='sm'
          >
            <Sparkles className='h-4 w-4' />
            Generate Executive Briefing
          </Button>
          {insights.length === 0 && (
            <p className='mt-2 text-xs text-muted-foreground'>
              Run analytical findings first before generating a briefing.
            </p>
          )}
        </CardContent>
      </Card>
    )
  }

  if (generating) {
    return (
      <Card>
        <CardContent className='flex flex-col items-center py-12'>
          <Loader2 className='mb-3 h-8 w-8 animate-spin text-primary' />
          <p className='text-sm text-muted-foreground'>
            Generating executive briefing...
          </p>
        </CardContent>
      </Card>
    )
  }

  if (!intelligence) return null

  return (
    <Card>
      <CardHeader className='pb-3'>
        <div className='flex items-center justify-between'>
          <CardTitle className='flex items-center gap-2'>
            <Bot className='h-4 w-4' />
            Executive Briefing
          </CardTitle>
          <div className='flex items-center gap-2'>
            <Badge
              variant='outline'
              className='border-amber-500/30 bg-amber-500/10 text-xs text-amber-600 dark:text-amber-400'
            >
              <FileWarning className='h-3 w-3' />
              {intelligence.label}
            </Badge>
            <Button
              onClick={handleGenerate}
              disabled={generating}
              variant='outline'
              size='sm'
            >
              <Sparkles className='h-3 w-3' />
              Regenerate Briefing
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className='space-y-4'>
        {error && (
          <div className='rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive'>
            {error}
          </div>
        )}

        {/* Narrative */}
        <div className='rounded-lg border bg-muted/30 p-4'>
          {intelligence.narrative.split('\n\n').map((para, i) => (
            <p
              key={i}
              className={cn('text-sm leading-relaxed', i > 0 && 'mt-3')}
            >
              {para}
            </p>
          ))}
        </div>

        {/* Claims */}
        {intelligence.claims.length > 0 && (
          <div>
            <button
              onClick={() => setExpandedClaims(!expandedClaims)}
              className='mb-2 flex w-full items-center gap-2 text-left'
            >
              <h4 className='text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
                Cited Claims ({intelligence.claims.length})
              </h4>
              <ChevronDown
                className={cn(
                  'h-3.5 w-3.5 text-muted-foreground transition-transform',
                  expandedClaims && 'rotate-180'
                )}
              />
            </button>

            {expandedClaims && (
              <div className='space-y-2'>
                {intelligence.claims.map((claim, i) => (
                  <div
                    key={i}
                    className='flex items-start gap-2 rounded-md border px-3 py-2'
                  >
                    <span className='mt-0.5 shrink-0 font-mono text-xs text-muted-foreground'>
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <div className='min-w-0 flex-1'>
                      <p className='text-sm'>
                        {claim.narrative_claim}
                        <CitationMarker
                          ids={claim.cited_insight_ids}
                          insights={insights}
                        />
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <p className='text-xs text-muted-foreground'>
          Generated{' '}
          {new Date(intelligence.created_at).toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          })}
        </p>
      </CardContent>
    </Card>
  )
}
