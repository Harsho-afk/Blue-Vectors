import { useState } from 'react'
import { AlertCircle, CheckCircle2, ChevronDown, Zap } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface CorrelationResult {
  id: number
  account_a_id: number
  account_b_id: number
  confidence: number
  a_platform?: string
  a_username?: string
  a_display_name?: string
  b_platform?: string
  b_username?: string
  b_display_name?: string
  shap_json: {
    confidence_pct?: number
    band?: string
    username_score?: number | null
    bio_score?: number | null
    temporal_score?: number | null
    notes?: string[]
  }
}

interface Account {
  id: number
  platform: string
  username: string
  display_name: string | null
}

interface Props {
  results: CorrelationResult[]
  accounts: Account[]
  isCorrelating: boolean
  onCorrelate: () => void
}

function bandVariant(band: string) {
  if (band === 'High') return 'default' as const
  if (band === 'Medium') return 'secondary' as const
  return 'destructive' as const
}

function SignalBar({ label, score }: { label: string; score?: number | null }) {
  const available = score != null
  return (
    <div className='space-y-1'>
      <div className='flex items-center justify-between text-sm'>
        <span className='text-foreground'>{label}</span>
        {available ? (
          <span className='font-mono text-primary'>
            {Math.round(score * 100)}%
          </span>
        ) : (
          <span className='text-xs text-muted-foreground'>
            Insufficient data
          </span>
        )}
      </div>
      {available && (
        <div className='h-1.5 w-full overflow-hidden rounded-full bg-muted'>
          <div
            className='h-full rounded-full bg-primary transition-all'
            style={{ width: `${score * 100}%` }}
          />
        </div>
      )}
    </div>
  )
}

function ResultRow({
  result,
  accounts,
  isExpanded,
  onToggle,
}: {
  result: CorrelationResult
  accounts: Account[]
  isExpanded: boolean
  onToggle: () => void
}) {
  const shap = result.shap_json || {}
  const confidence = shap.confidence_pct ?? result.confidence ?? 0
  const band = shap.band || 'Low'

  const accA = accounts.find((a) => a.id === result.account_a_id)
  const accB = accounts.find((a) => a.id === result.account_b_id)

  const aPlatform = result.a_platform || accA?.platform || '?'
  const bPlatform = result.b_platform || accB?.platform || '?'
  const aName =
    result.a_display_name || result.a_username || accA?.display_name || accA?.username || '?'
  const bName =
    result.b_display_name || result.b_username || accB?.display_name || accB?.username || '?'

  return (
    <div className='overflow-hidden rounded-lg border transition-colors hover:border-muted-foreground/50'>
      <button
        onClick={onToggle}
        className='flex w-full items-center justify-between gap-4 bg-background p-4 text-left transition-colors hover:bg-muted/30'
      >
        <div className='flex min-w-0 flex-1 items-center gap-3'>
          <div className='flex items-center gap-2'>
            <Badge variant='secondary' className='font-mono text-xs'>
              {aPlatform}
            </Badge>
            <span className='truncate font-mono text-sm'>{aName}</span>
          </div>
          <span className='shrink-0 text-sm text-muted-foreground'>↔</span>
          <div className='flex items-center gap-2'>
            <Badge variant='secondary' className='font-mono text-xs'>
              {bPlatform}
            </Badge>
            <span className='truncate font-mono text-sm'>{bName}</span>
          </div>
        </div>

        <div className='flex shrink-0 items-center gap-3'>
          <div className='flex items-center gap-2'>
            <div className='w-[100px]'>
              <div className='relative h-2 w-full overflow-hidden rounded-full bg-muted'>
                <div
                  className='h-full rounded-full bg-primary transition-all'
                  style={{ width: `${confidence}%` }}
                />
              </div>
            </div>
            <span className='w-10 text-right font-mono text-sm'>
              {confidence}%
            </span>
          </div>
          <Badge variant={bandVariant(band)}>{band}</Badge>
          <ChevronDown
            size={16}
            className={cn(
              'shrink-0 text-muted-foreground transition-transform duration-200',
              isExpanded && 'rotate-180'
            )}
          />
        </div>
      </button>

      {isExpanded && (
        <div className='space-y-4 border-t p-4'>
          <div className='space-y-3'>
            <h4 className='text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
              Signal Breakdown
            </h4>
            <SignalBar label='Username Match' score={shap.username_score} />
            <SignalBar label='Bio Similarity' score={shap.bio_score} />
            <SignalBar label='Temporal Pattern' score={shap.temporal_score} />
          </div>

          {shap.notes && shap.notes.length > 0 && (
            <div className='space-y-2 border-t pt-4'>
              <h4 className='text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
                Notes
              </h4>
              <ul className='space-y-1'>
                {shap.notes.map((note, idx) => (
                  <li key={idx} className='flex items-start gap-2 text-sm'>
                    <CheckCircle2
                      size={16}
                      className='mt-0.5 shrink-0 text-primary'
                    />
                    <span>{note}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function CorrelationResults({
  results,
  accounts,
  isCorrelating,
  onCorrelate,
}: Props) {
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())

  const toggleExpanded = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const canCorrelate = accounts.length >= 2
  const hasResults = results.length > 0

  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-4'>
        <CardTitle>Identity Correlation</CardTitle>
        <div className='flex items-center gap-2'>
          {!canCorrelate && (
            <span className='text-xs text-muted-foreground'>
              Collect at least 2 accounts to run correlation.
            </span>
          )}
          <Button
            onClick={onCorrelate}
            disabled={isCorrelating || !canCorrelate}
            size='sm'
          >
            <Zap size={16} />
            {isCorrelating ? 'Correlating...' : 'Correlate'}
          </Button>
        </div>
      </CardHeader>

      <CardContent className='space-y-3'>
        {!hasResults && canCorrelate && !isCorrelating && (
          <div className='flex items-center gap-3 rounded-lg border p-4'>
            <AlertCircle size={18} className='shrink-0 text-muted-foreground' />
            <p className='text-sm text-muted-foreground'>
              No correlations run yet. Click Correlate to analyze.
            </p>
          </div>
        )}

        {isCorrelating && (
          <div className='space-y-2'>
            {[0, 1].map((idx) => (
              <div
                key={idx}
                className='h-16 animate-pulse rounded-lg border bg-muted/50'
              />
            ))}
          </div>
        )}

        {hasResults && !isCorrelating && (
          <div className='space-y-2'>
            {results.map((result, i) => (
              <ResultRow
                key={result.id || i}
                result={result}
                accounts={accounts}
                isExpanded={expandedIds.has(result.id)}
                onToggle={() => toggleExpanded(result.id)}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
