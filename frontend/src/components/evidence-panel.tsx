import { useState } from 'react'
import {
  ChevronDown,
  FileText,
  Lightbulb,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface Insight {
  id: number
  account_id: number | null
  category: string
  claim: string
  confidence: number
  evidence: Record<string, unknown>
  created_at: string
}

interface Account {
  id: number
  platform: string
  username: string
  display_name: string | null
}

interface Props {
  insights: Insight[]
  accounts?: Account[]
}

const CATEGORY_LABELS: Record<string, string> = {
  temporal: 'Temporal',
  keyword: 'Keywords',
  hashtag: 'Hashtags',
  topic: 'Topics',
  sentiment: 'Sentiment',
  location: 'Location',
  consistency: 'Consistency',
  identity: 'Identity',
}

function confidenceBand(c: number): { label: string; color: string } {
  if (c >= 0.75) return { label: 'High', color: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30' }
  if (c >= 0.45) return { label: 'Medium', color: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30' }
  return { label: 'Low', color: 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30' }
}

function formatEvidence(evidence: Record<string, unknown>): { key: string; value: string }[] {
  const entries: { key: string; value: string }[] = []
  for (const [k, v] of Object.entries(evidence)) {
    if (v == null) continue
    const label = k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
    if (typeof v === 'object' && !Array.isArray(v)) {
      entries.push({ key: label, value: JSON.stringify(v, null, 2) })
    } else if (Array.isArray(v)) {
      entries.push({ key: label, value: v.join(', ') })
    } else {
      entries.push({ key: label, value: String(v) })
    }
  }
  return entries
}

function InsightCard({
  insight,
  account,
}: {
  insight: Insight
  account?: Account
}) {
  const [expanded, setExpanded] = useState(false)
  const band = confidenceBand(insight.confidence)
  const evidenceEntries = formatEvidence(insight.evidence || {})

  return (
    <div className='rounded-lg border bg-background transition-colors hover:border-muted-foreground/30'>
      <button
        onClick={() => setExpanded(!expanded)}
        className='flex w-full items-start gap-3 p-3 text-left'
      >
        <Lightbulb className='mt-0.5 h-4 w-4 shrink-0 text-primary' />
        <div className='min-w-0 flex-1'>
          <div className='mb-1 flex flex-wrap items-center gap-1.5'>
            <Badge variant='outline' className='text-xs'>
              {CATEGORY_LABELS[insight.category] || insight.category}
            </Badge>
            {account && (
              <span className='text-xs text-muted-foreground'>
                {account.platform}: {account.username}
              </span>
            )}
            <Badge className={cn('border text-xs', band.color)}>
              {band.label} ({Math.round(insight.confidence * 100)}%)
            </Badge>
          </div>
          <p className='text-sm'>{insight.claim}</p>
        </div>
        {evidenceEntries.length > 0 && (
          <ChevronDown
            className={cn(
              'mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform',
              expanded && 'rotate-180'
            )}
          />
        )}
      </button>

      {expanded && evidenceEntries.length > 0 && (
        <div className='border-t px-3 py-2'>
          <p className='mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
            Evidence
          </p>
          <div className='space-y-1'>
            {evidenceEntries.map((e, i) => (
              <div key={i} className='flex gap-2 text-xs'>
                <span className='shrink-0 font-medium text-muted-foreground'>
                  {e.key}:
                </span>
                <span className='break-all text-foreground'>{e.value}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export function EvidencePanel({ insights, accounts }: Props) {
  const [filter, setFilter] = useState<string>('all')

  if (insights.length === 0) {
    return (
      <Card>
        <CardContent className='py-12 text-center'>
          <FileText className='mx-auto mb-2 h-8 w-8 text-muted-foreground' />
          <p className='text-sm text-muted-foreground'>
            No insights generated yet. Run the investigation to compute insights.
          </p>
        </CardContent>
      </Card>
    )
  }

  const categories = ['all', ...new Set(insights.map((i) => i.category))]
  const filtered =
    filter === 'all' ? insights : insights.filter((i) => i.category === filter)

  const accountMap = new Map(accounts?.map((a) => [a.id, a]))

  return (
    <Card>
      <CardHeader className='pb-3'>
        <div className='flex items-center justify-between'>
          <CardTitle className='flex items-center gap-2'>
            <Lightbulb className='h-4 w-4' />
            Insights ({insights.length})
          </CardTitle>
        </div>
        <div className='flex flex-wrap gap-1 pt-1'>
          {categories.map((cat) => (
            <Button
              key={cat}
              variant={filter === cat ? 'default' : 'ghost'}
              size='sm'
              className='h-7 text-xs'
              onClick={() => setFilter(cat)}
            >
              {cat === 'all'
                ? 'All'
                : CATEGORY_LABELS[cat] || cat}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent className='space-y-2'>
        {filtered.map((insight) => (
          <InsightCard
            key={insight.id}
            insight={insight}
            account={
              insight.account_id
                ? accountMap.get(insight.account_id)
                : undefined
            }
          />
        ))}
      </CardContent>
    </Card>
  )
}
