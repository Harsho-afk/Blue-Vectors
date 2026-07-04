import { useState } from 'react'
import {
  ChevronDown,
  ExternalLink,
  Globe,
  Mail,
  AtSign,
  Link2,
  Sparkles,
  LayoutTemplate,
  Import,
  Copy,
  Check,
} from 'lucide-react'
import { API } from '@/lib/aria-api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'

interface DorkingResult {
  title: string
  url: string
  snippet: string
  source: string
  query: string
  retrieved_at: string
  lead_score: number
  lead_band: 'high' | 'medium' | 'low'
  signals: string[]
}

interface DorkingQuery {
  query: string
  purpose: string
  source: 'template' | 'llm'
  result_count: number
}

interface DorkingEntity {
  type: string
  value: string
  platform?: string
  username?: string
  source_url: string
}

interface DorkingSummary {
  total_queries: number
  template_queries: number
  llm_queries: number
  blocked_queries: number
  total_results: number
  high_leads: number
  medium_leads: number
  low_leads: number
  entities_found: number
}

interface DorkingLookup {
  id: number
  lookup_type: string
  input_value?: string
  result?: {
    identifier_type: string
    identifier_value: string
    queries_executed: DorkingQuery[]
    results: DorkingResult[]
    entities: DorkingEntity[]
    summary: DorkingSummary
  }
}

interface Props {
  lookup: DorkingLookup
  caseId: string
  onAccountImported?: () => void
}

function bandColor(band: string) {
  switch (band) {
    case 'high':
      return 'bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/30'
    case 'medium':
      return 'bg-yellow-500/15 text-yellow-700 dark:text-yellow-400 border-yellow-500/30'
    default:
      return 'bg-muted text-muted-foreground'
  }
}

function entityIcon(type: string) {
  switch (type) {
    case 'email':
      return <Mail className='h-3 w-3' />
    case 'handle':
      return <AtSign className='h-3 w-3' />
    case 'profile_url':
      return <Link2 className='h-3 w-3' />
    default:
      return <Globe className='h-3 w-3' />
  }
}

export function DorkingResults({ lookup, caseId, onAccountImported }: Props) {
  const [showQueries, setShowQueries] = useState(false)
  const [showLowLeads, setShowLowLeads] = useState(false)
  const [importing, setImporting] = useState<string | null>(null)
  const [copied, setCopied] = useState<string | null>(null)

  const data = lookup.result
  if (!data) return null

  const { summary, results, entities, queries_executed } = data

  const highMedResults = results.filter((r) => r.lead_band !== 'low')
  const lowResults = results.filter((r) => r.lead_band === 'low')

  const handleImportAccount = async (entity: DorkingEntity) => {
    if (!entity.platform || !entity.username) return
    setImporting(entity.value)
    try {
      const res = await fetch(
        `${API}/api/cases/${caseId}/osint/import-account`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            platform: entity.platform,
            username: entity.username,
            url: entity.value,
          }),
        }
      )
      if (res.ok) {
        onAccountImported?.()
      }
    } catch {
      // silent fail
    } finally {
      setImporting(null)
    }
  }

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(text)
    setTimeout(() => setCopied(null), 2000)
  }

  return (
    <div className='space-y-3'>
      {/* Summary Bar */}
      <div className='flex flex-wrap items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2'>
        <span className='text-sm font-medium'>
          Dorking: {lookup.input_value}
        </span>
        <Badge variant='outline' className='text-xs'>
          {summary.total_queries} queries
        </Badge>
        <Badge variant='outline' className='text-xs'>
          {summary.total_results} results
        </Badge>
        {summary.high_leads > 0 && (
          <Badge className={bandColor('high')}>{summary.high_leads} high</Badge>
        )}
        {summary.medium_leads > 0 && (
          <Badge className={bandColor('medium')}>
            {summary.medium_leads} medium
          </Badge>
        )}
        {summary.low_leads > 0 && (
          <Badge variant='secondary'>{summary.low_leads} low</Badge>
        )}
        {summary.entities_found > 0 && (
          <Badge variant='outline' className='text-xs'>
            {summary.entities_found} entities extracted
          </Badge>
        )}
        {summary.llm_queries > 0 && (
          <Badge
            variant='outline'
            className='border-purple-500/30 bg-purple-500/10 text-xs text-purple-700 dark:text-purple-400'
          >
            <Sparkles className='mr-1 h-3 w-3' />
            AI expanded
          </Badge>
        )}
      </div>

      {/* Extracted Entities */}
      {entities.length > 0 && (
        <Card>
          <CardHeader className='pb-2'>
            <CardTitle className='text-sm'>Extracted Entities</CardTitle>
            <CardDescription className='text-xs'>
              Usernames, emails, and profiles found in search results
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className='flex flex-wrap gap-2'>
              {entities.map((entity, i) => (
                <div
                  key={i}
                  className='flex items-center gap-1.5 rounded-md border bg-background px-2 py-1'
                >
                  {entityIcon(entity.type)}
                  <span className='max-w-[200px] truncate font-mono text-xs'>
                    {entity.username
                      ? `${entity.platform}/${entity.username}`
                      : entity.value}
                  </span>
                  {entity.platform && entity.username && (
                    <Button
                      variant='ghost'
                      size='sm'
                      className='h-5 px-1'
                      disabled={importing === entity.value}
                      onClick={() => handleImportAccount(entity)}
                    >
                      {importing === entity.value ? (
                        <Check className='h-3 w-3 text-green-500' />
                      ) : (
                        <Import className='h-3 w-3' />
                      )}
                    </Button>
                  )}
                  <Button
                    variant='ghost'
                    size='sm'
                    className='h-5 px-1'
                    onClick={() => handleCopy(entity.value)}
                  >
                    {copied === entity.value ? (
                      <Check className='h-3 w-3 text-green-500' />
                    ) : (
                      <Copy className='h-3 w-3' />
                    )}
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* High + Medium Leads */}
      {highMedResults.length > 0 && (
        <div className='space-y-2'>
          {highMedResults.map((r, i) => (
            <ResultRow key={i} result={r} />
          ))}
        </div>
      )}

      {highMedResults.length === 0 && lowResults.length === 0 && (
        <div className='rounded-lg border border-dashed px-4 py-6 text-center text-sm text-muted-foreground'>
          No results found for this identifier.
        </div>
      )}

      {/* Low Leads (collapsed) */}
      {lowResults.length > 0 && (
        <Collapsible open={showLowLeads} onOpenChange={setShowLowLeads}>
          <CollapsibleTrigger asChild>
            <Button variant='ghost' size='sm' className='w-full'>
              <ChevronDown
                className={`mr-1 h-3 w-3 transition-transform ${showLowLeads ? '' : '-rotate-90'}`}
              />
              {lowResults.length} low-confidence leads
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className='space-y-2 pt-2'>
            {lowResults.map((r, i) => (
              <ResultRow key={i} result={r} />
            ))}
          </CollapsibleContent>
        </Collapsible>
      )}

      {/* Query Log (collapsed) */}
      <Collapsible open={showQueries} onOpenChange={setShowQueries}>
        <CollapsibleTrigger asChild>
          <Button variant='ghost' size='sm' className='w-full'>
            <ChevronDown
              className={`mr-1 h-3 w-3 transition-transform ${showQueries ? '' : '-rotate-90'}`}
            />
            View {queries_executed.length} search queries
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className='pt-2'>
          <div className='max-h-[300px] space-y-1 overflow-y-auto rounded-lg border p-2'>
            {queries_executed.map((q, i) => (
              <div
                key={i}
                className='flex items-start gap-2 rounded px-2 py-1 text-xs hover:bg-muted/50'
              >
                {q.source === 'llm' ? (
                  <Sparkles className='mt-0.5 h-3 w-3 shrink-0 text-purple-500' />
                ) : (
                  <LayoutTemplate className='mt-0.5 h-3 w-3 shrink-0 text-muted-foreground' />
                )}
                <div className='min-w-0 flex-1'>
                  <span className='font-mono'>{q.query}</span>
                  <span className='ml-2 text-muted-foreground'>
                    — {q.purpose}
                  </span>
                </div>
                <Badge variant='secondary' className='shrink-0 text-[10px]'>
                  {q.result_count}
                </Badge>
              </div>
            ))}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}

function ResultRow({ result }: { result: DorkingResult }) {
  return (
    <div className='group flex items-start gap-3 rounded-lg border px-3 py-2 transition-colors hover:bg-muted/30'>
      <div className='mt-0.5'>
        <Badge className={`text-[10px] ${bandColor(result.lead_band)}`}>
          {result.lead_score}
        </Badge>
      </div>
      <div className='min-w-0 flex-1'>
        <a
          href={result.url}
          target='_blank'
          rel='noopener noreferrer'
          className='flex items-center gap-1 text-sm font-medium text-foreground hover:underline'
        >
          <span className='truncate'>{result.title || result.url}</span>
          <ExternalLink className='h-3 w-3 shrink-0 opacity-0 transition-opacity group-hover:opacity-100' />
        </a>
        <p className='truncate text-xs text-muted-foreground'>{result.url}</p>
        {result.snippet && (
          <p className='mt-0.5 line-clamp-2 text-xs text-muted-foreground'>
            {result.snippet}
          </p>
        )}
        <div className='mt-1 flex flex-wrap gap-1'>
          {result.signals.map((s, i) => (
            <span
              key={i}
              className='rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground'
            >
              {s.replace(/_/g, ' ')}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
