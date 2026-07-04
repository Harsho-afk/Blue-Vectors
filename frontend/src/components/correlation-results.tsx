import { useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Loader2,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'

interface ShapData {
  confidence_pct?: number
  band?: string
  evidence_type?: string
  username_score?: number | null
  username_raw?: number | null
  username_distinctiveness?: number | null
  bio_score?: number | null
  temporal_score?: number | null
  community_score?: number | null
  stylometry_score?: number | null
  geo_agreement?: number | null
  tier1_links?: string[]
  notes?: string[]
}

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
  shap_json: ShapData
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
  onCorrelate: (accountAId?: number, accountBId?: number) => void
}

function bandVariant(band: string) {
  if (band === 'High') return 'default' as const
  if (band === 'Medium') return 'secondary' as const
  return 'destructive' as const
}

const SIGNAL_DEFS = [
  { key: 'username_score', label: 'Username Match' },
  { key: 'bio_score', label: 'Bio Similarity' },
  { key: 'temporal_score', label: 'Temporal Pattern' },
  { key: 'community_score', label: 'Community Overlap' },
  { key: 'stylometry_score', label: 'Writing Style' },
  { key: 'geo_agreement', label: 'Geo Agreement' },
] as const

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
  const shap: ShapData = result.shap_json || {}
  const confidence = shap.confidence_pct ?? result.confidence ?? 0
  const band = shap.band || 'Low'

  const accA = accounts.find((a) => a.id === result.account_a_id)
  const accB = accounts.find((a) => a.id === result.account_b_id)

  const aPlatform = result.a_platform || accA?.platform || '?'
  const bPlatform = result.b_platform || accB?.platform || '?'
  const aName =
    result.a_display_name ||
    result.a_username ||
    accA?.display_name ||
    accA?.username ||
    '?'
  const bName =
    result.b_display_name ||
    result.b_username ||
    accB?.display_name ||
    accB?.username ||
    '?'

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
            {SIGNAL_DEFS.map(({ key, label }) => (
              <SignalBar
                key={key}
                label={label}
                score={shap[key] as number | null | undefined}
              />
            ))}
          </div>

          {shap.tier1_links && shap.tier1_links.length > 0 && (
            <div className='space-y-2 border-t pt-4'>
              <h4 className='text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
                Hard Links
              </h4>
              <ul className='space-y-1'>
                {shap.tier1_links.map((link, idx) => (
                  <li key={idx} className='flex items-start gap-2 text-sm'>
                    <CheckCircle2
                      size={16}
                      className='mt-0.5 shrink-0 text-green-500'
                    />
                    <span>{link}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

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
  const [mode, setMode] = useState<'all' | 'pair'>('all')
  const [selectedA, setSelectedA] = useState<string>('')
  const [selectedB, setSelectedB] = useState<string>('')

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

  const handleRun = () => {
    if (mode === 'pair') {
      const aId = parseInt(selectedA, 10)
      const bId = parseInt(selectedB, 10)
      if (!isNaN(aId) && !isNaN(bId) && aId !== bId) {
        onCorrelate(aId, bId)
      }
    } else {
      onCorrelate()
    }
  }

  const pairValid =
    mode === 'pair' &&
    selectedA &&
    selectedB &&
    selectedA !== selectedB

  const runDisabled =
    isCorrelating ||
    !canCorrelate ||
    (mode === 'pair' && !pairValid)

  return (
    <Card>
      <CardHeader className='space-y-4 pb-4'>
        <div className='flex flex-row items-center justify-between space-y-0'>
          <CardTitle>Identity Correlation</CardTitle>
          <div className='flex items-center gap-2'>
            {!canCorrelate && (
              <span className='text-xs text-muted-foreground'>
                Collect at least 2 accounts to run correlation.
              </span>
            )}
            <Button
              onClick={handleRun}
              disabled={runDisabled}
              size='sm'
            >
              {isCorrelating ? (
                <>
                  <Loader2 size={16} className='animate-spin' />
                  Correlating...
                </>
              ) : (
                <>
                  <Zap size={16} />
                  Correlate
                </>
              )}
            </Button>
          </div>
        </div>

        {canCorrelate && (
          <div className='flex flex-wrap items-end gap-3'>
            <div className='flex gap-1 rounded-lg border p-1'>
              <Button
                variant={mode === 'all' ? 'default' : 'ghost'}
                size='sm'
                className='h-7 text-xs'
                onClick={() => setMode('all')}
                disabled={isCorrelating}
              >
                All Pairs
              </Button>
              <Button
                variant={mode === 'pair' ? 'default' : 'ghost'}
                size='sm'
                className='h-7 text-xs'
                onClick={() => setMode('pair')}
                disabled={isCorrelating}
              >
                Custom Pair
              </Button>
            </div>

            {mode === 'pair' && (
              <div className='flex items-center gap-2'>
                <Select
                  value={selectedA}
                  onValueChange={setSelectedA}
                  disabled={isCorrelating}
                >
                  <SelectTrigger className='h-8 w-[200px]'>
                    <SelectValue placeholder='Account A' />
                  </SelectTrigger>
                  <SelectContent>
                    {accounts.map((acc) => (
                      <SelectItem
                        key={acc.id}
                        value={String(acc.id)}
                        disabled={String(acc.id) === selectedB}
                      >
                        {acc.platform}: {acc.display_name || acc.username}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <span className='text-sm text-muted-foreground'>vs</span>

                <Select
                  value={selectedB}
                  onValueChange={setSelectedB}
                  disabled={isCorrelating}
                >
                  <SelectTrigger className='h-8 w-[200px]'>
                    <SelectValue placeholder='Account B' />
                  </SelectTrigger>
                  <SelectContent>
                    {accounts.map((acc) => (
                      <SelectItem
                        key={acc.id}
                        value={String(acc.id)}
                        disabled={String(acc.id) === selectedA}
                      >
                        {acc.platform}: {acc.display_name || acc.username}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        )}
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
