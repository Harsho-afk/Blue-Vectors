import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Clock,
  Download,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCw,
  Shield,
  X,
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
import { cn } from '@/lib/utils'

// ── Types ──

interface ReadinessData {
  ready: boolean
  warnings: string[]
  data_available: {
    accounts: number
    correlations: number
    insights: number
    lookups: number
    intelligence: boolean
  }
}

interface ReportVersion {
  id: number
  version: number
  status: 'generating' | 'ready' | 'failed'
  methodology_version: string
  generated_at: string
  content_hash: string | null
  error_message: string | null
}

interface ReportJson {
  report_metadata: {
    case_id: number
    case_title: string
    case_status: string
    investigator: string
    generated_at: string
    methodology_version: string
  }
  executive_summary: {
    total_accounts_collected: number
    total_platforms: number
    total_correlations: number
    correlation_bands: Record<string, number>
    total_insights: number
    insight_categories: Record<string, number>
    total_sources: number
    total_lookups: number
  }
  identified_accounts: {
    collected_accounts: Array<{
      reference_id: string
      platform: string
      username: string
      display_name: string | null
      post_count: number
      collection_status: string
    }>
    discovered_leads: Array<{
      platform: string
      username: string
      url: string | null
      status: string
    }>
    total_collected: number
    total_leads: number
  }
  correlation_findings: Array<{
    reference_id: string
    account_a: { ref: string; platform: string; username: string }
    account_b: { ref: string; platform: string; username: string }
    confidence_pct: number
    band: string
    evidence_type: string
    conclusion: string
  }>
  limitations: string[]
  confidence_notes: {
    band_definitions: Record<string, string>
    disclaimer: string
  }
  intelligence_briefing: {
    label: string
    narrative: string
    disclaimer: string
  } | null
}

interface Props {
  caseId: string
}

export function ReportsPanel({ caseId }: Props) {
  const [readiness, setReadiness] = useState<ReadinessData | null>(null)
  const [reports, setReports] = useState<ReportVersion[]>([])
  const [generating, setGenerating] = useState(false)
  const [activeReport, setActiveReport] = useState<ReportJson | null>(null)
  const [activeReportId, setActiveReportId] = useState<number | null>(null)
  const [loadingReport, setLoadingReport] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchReadiness = useCallback(() => {
    fetch(`${API}/api/cases/${caseId}/reports/readiness`, {
      credentials: 'include',
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => data && setReadiness(data))
      .catch(() => {})
  }, [caseId])

  const fetchReports = useCallback(() => {
    fetch(`${API}/api/cases/${caseId}/reports`, { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : { reports: [] }))
      .then((data) => setReports(data.reports || []))
      .catch(() => {})
  }, [caseId])

  useEffect(() => {
    fetchReadiness()
    fetchReports()
  }, [fetchReadiness, fetchReports])

  const handleGenerate = async () => {
    setGenerating(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/cases/${caseId}/reports`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }
      const data = await res.json()
      fetchReports()
      loadReport(data.report_id)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setGenerating(false)
    }
  }

  const loadReport = async (reportId: number) => {
    setLoadingReport(true)
    setError(null)
    try {
      const res = await fetch(
        `${API}/api/cases/${caseId}/reports/${reportId}`,
        { credentials: 'include' }
      )
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setActiveReport(data.report_json)
      setActiveReportId(reportId)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoadingReport(false)
    }
  }

  const openHtml = (reportId: number) => {
    window.open(
      `${API}/api/cases/${caseId}/reports/${reportId}/html`,
      '_blank'
    )
  }

  const downloadPdf = (reportId: number) => {
    window.open(
      `${API}/api/cases/${caseId}/reports/${reportId}/pdf`,
      '_blank'
    )
  }

  return (
    <div className='space-y-4'>
      {/* Readiness check */}
      <ReadinessCard readiness={readiness} />

      {/* Generate button */}
      <div className='flex items-center gap-3'>
        <Button
          onClick={handleGenerate}
          disabled={generating}
          className='gap-2'
        >
          {generating ? (
            <Loader2 className='size-4 animate-spin' />
          ) : (
            <FileText className='size-4' />
          )}
          {generating ? 'Generating...' : 'Generate Report'}
        </Button>
        <Button variant='ghost' size='sm' onClick={fetchReports}>
          <RefreshCw className='size-4' />
        </Button>
      </div>

      {error && (
        <Card className='border-destructive'>
          <CardContent className='flex items-center gap-2 pt-4 text-sm text-destructive'>
            <X className='size-4 shrink-0' />
            {error}
          </CardContent>
        </Card>
      )}

      {/* Report history */}
      {reports.length > 0 && (
        <Card>
          <CardHeader className='pb-3'>
            <CardTitle className='text-base'>Report Versions</CardTitle>
            <CardDescription>
              {reports.length} version{reports.length > 1 ? 's' : ''} generated
            </CardDescription>
          </CardHeader>
          <CardContent className='space-y-2'>
            {reports.map((r) => (
              <div
                key={r.id}
                className={cn(
                  'flex items-center justify-between rounded-md border p-3 text-sm',
                  activeReportId === r.id && 'border-primary bg-muted/50'
                )}
              >
                <div className='flex items-center gap-3'>
                  <Badge
                    variant={
                      r.status === 'ready'
                        ? 'default'
                        : r.status === 'failed'
                          ? 'destructive'
                          : 'secondary'
                    }
                    className='text-xs'
                  >
                    {r.status}
                  </Badge>
                  <span className='font-medium'>v{r.version}</span>
                  <span className='text-muted-foreground'>
                    {new Date(r.generated_at).toLocaleString()}
                  </span>
                </div>
                <div className='flex items-center gap-2'>
                  {r.status === 'ready' && (
                    <>
                      <Button
                        variant='ghost'
                        size='sm'
                        onClick={() => loadReport(r.id)}
                      >
                        View
                      </Button>
                      <Button
                        variant='ghost'
                        size='sm'
                        onClick={() => openHtml(r.id)}
                        title='View HTML report'
                      >
                        <ExternalLink className='size-3.5' />
                      </Button>
                      <Button
                        variant='ghost'
                        size='sm'
                        onClick={() => downloadPdf(r.id)}
                        title='Download PDF report'
                      >
                        <Download className='size-3.5' />
                      </Button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Report preview */}
      {loadingReport && (
        <Card>
          <CardContent className='flex items-center justify-center py-12'>
            <Loader2 className='size-6 animate-spin text-muted-foreground' />
          </CardContent>
        </Card>
      )}

      {activeReport && !loadingReport && (
        <ReportPreview
          report={activeReport}
          reportId={activeReportId!}
          caseId={caseId}
          onOpenHtml={() => openHtml(activeReportId!)}
          onDownloadPdf={() => downloadPdf(activeReportId!)}
        />
      )}
    </div>
  )
}

// ── Readiness Card ──

function ReadinessCard({ readiness }: { readiness: ReadinessData | null }) {
  if (!readiness) return null

  const data = readiness.data_available

  return (
    <Card>
      <CardHeader className='pb-3'>
        <CardTitle className='flex items-center gap-2 text-base'>
          <Shield className='size-4' />
          Report Readiness
        </CardTitle>
      </CardHeader>
      <CardContent className='space-y-3'>
        <div className='grid grid-cols-2 gap-2 text-sm sm:grid-cols-5'>
          <ReadinessItem
            label='Accounts'
            value={data.accounts}
            ok={data.accounts > 0}
          />
          <ReadinessItem
            label='Correlations'
            value={data.correlations}
            ok={data.correlations > 0}
          />
          <ReadinessItem
            label='Insights'
            value={data.insights}
            ok={data.insights > 0}
          />
          <ReadinessItem
            label='Lookups'
            value={data.lookups}
            ok={data.lookups > 0}
          />
          <ReadinessItem
            label='Intelligence'
            value={data.intelligence ? 'Yes' : 'No'}
            ok={data.intelligence}
          />
        </div>
        {readiness.warnings.length > 0 && (
          <div className='space-y-1'>
            {readiness.warnings.map((w, i) => (
              <p
                key={i}
                className='flex items-start gap-2 text-xs text-amber-600 dark:text-amber-400'
              >
                <AlertTriangle className='mt-0.5 size-3 shrink-0' />
                {w}
              </p>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function ReadinessItem({
  label,
  value,
  ok,
}: {
  label: string
  value: number | string
  ok: boolean
}) {
  return (
    <div className='flex items-center gap-2'>
      {ok ? (
        <Check className='size-3.5 text-green-600 dark:text-green-400' />
      ) : (
        <X className='size-3.5 text-muted-foreground' />
      )}
      <span className='text-muted-foreground'>{label}:</span>
      <span className='font-medium'>{value}</span>
    </div>
  )
}

// ── Report Preview ──

function ReportPreview({
  report,
  onOpenHtml,
  onDownloadPdf,
}: {
  report: ReportJson
  reportId: number
  caseId: string
  onOpenHtml: () => void
  onDownloadPdf: () => void
}) {
  const meta = report.report_metadata
  const summary = report.executive_summary
  const accounts = report.identified_accounts
  const correlations = report.correlation_findings
  const limitations = report.limitations
  const confidence = report.confidence_notes
  const intelligence = report.intelligence_briefing

  return (
    <div className='space-y-4'>
      {/* Header */}
      <Card className="overflow-hidden border-orange-500/30 bg-gradient-to-r from-orange-500/10 via-transparent to-transparent">
        <CardHeader className="py-4">
          <div className='flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between'>
            <div className='flex items-center gap-3'>
              <img
                src='/images/aria-logo.png'
                alt='ARIA Logo'
                className='h-12 w-12 shrink-0 object-contain filter dark:drop-shadow-[0_0_8px_rgba(249,115,22,0.3)]'
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                }}
              />
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-bold uppercase tracking-widest text-orange-500">
                    ARIA SOCMINT
                  </span>
                  <Badge variant="outline" className="border-orange-500/40 text-orange-500 text-[0.65rem] font-mono uppercase">
                    v{meta.methodology_version}
                  </Badge>
                </div>
                <CardTitle className="text-xl font-extrabold tracking-tight">
                  {meta.case_title}
                </CardTitle>
                <CardDescription className="font-mono text-xs">
                  Generated: {new Date(meta.generated_at).toLocaleString()} | Investigator: {meta.investigator}
                </CardDescription>
              </div>
            </div>
            <div className='flex items-center gap-2 self-end sm:self-center'>
              <Button variant='outline' size='sm' onClick={onOpenHtml} className="border-orange-500/30 hover:bg-orange-500/10 text-orange-500 hover:text-orange-600">
                <ExternalLink className='mr-2 size-3.5' />
                Full Report
              </Button>
              <Button variant='outline' size='sm' onClick={onDownloadPdf} className="border-orange-500/30 hover:bg-orange-500/10 text-orange-500 hover:text-orange-600">
                <Download className='mr-2 size-3.5' />
                Download PDF
              </Button>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* Executive Summary */}
      <Card>
        <CardHeader className='pb-3'>
          <CardTitle className='text-base'>Executive Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <div className='grid grid-cols-2 gap-4 text-sm sm:grid-cols-4'>
            <StatTile label='Accounts' value={summary.total_accounts_collected} />
            <StatTile label='Platforms' value={summary.total_platforms} />
            <StatTile label='Correlations' value={summary.total_correlations} />
            <StatTile label='Insights' value={summary.total_insights} />
          </div>
          <div className='mt-3 flex flex-wrap gap-2'>
            {Object.entries(summary.correlation_bands).map(([band, count]) =>
              count > 0 ? (
                <Badge
                  key={band}
                  variant={
                    band === 'High'
                      ? 'default'
                      : band === 'Medium'
                        ? 'secondary'
                        : 'outline'
                  }
                  className={cn(
                    band === 'High' &&
                      'bg-green-600 text-white dark:bg-green-700',
                    band === 'Medium' &&
                      'bg-amber-500 text-white dark:bg-amber-600'
                  )}
                >
                  {count} {band}
                </Badge>
              ) : null
            )}
          </div>
        </CardContent>
      </Card>

      {/* Correlation Findings */}
      {correlations.length > 0 && (
        <Card>
          <CardHeader className='pb-3'>
            <CardTitle className='text-base'>
              Correlation Findings ({correlations.length})
            </CardTitle>
          </CardHeader>
          <CardContent className='space-y-3'>
            {correlations.map((c) => (
              <Collapsible key={c.reference_id}>
                <CollapsibleTrigger className='flex w-full items-center justify-between rounded-md border p-3 text-left text-sm hover:bg-muted/50'>
                  <div className='flex items-center gap-3'>
                    <Badge
                      className={cn(
                        'text-xs text-white',
                        c.band === 'High' && 'bg-green-600 dark:bg-green-700',
                        c.band === 'Medium' && 'bg-amber-500 dark:bg-amber-600',
                        c.band === 'Low' && 'bg-slate-500 dark:bg-slate-600'
                      )}
                    >
                      {c.band}
                    </Badge>
                    <span>
                      {c.account_a.platform}/{c.account_a.username} ↔{' '}
                      {c.account_b.platform}/{c.account_b.username}
                    </span>
                    <span className='font-mono text-muted-foreground'>
                      {c.confidence_pct.toFixed(1)}%
                    </span>
                  </div>
                  <ChevronDown className='size-4 text-muted-foreground' />
                </CollapsibleTrigger>
                <CollapsibleContent className='px-3 pb-3 pt-2'>
                  <p className='text-sm text-muted-foreground'>
                    {c.conclusion}
                  </p>
                  <p className='mt-1 text-xs text-muted-foreground'>
                    Evidence type: {c.evidence_type} | Ref: {c.reference_id}
                  </p>
                </CollapsibleContent>
              </Collapsible>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Accounts summary */}
      <Card>
        <CardHeader className='pb-3'>
          <CardTitle className='text-base'>
            Identified Accounts ({accounts.total_collected} collected,{' '}
            {accounts.total_leads} leads)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className='overflow-x-auto'>
            <table className='w-full text-sm'>
              <thead>
                <tr className='border-b text-left text-muted-foreground'>
                  <th className='p-2'>Ref</th>
                  <th className='p-2'>Platform</th>
                  <th className='p-2'>Username</th>
                  <th className='p-2'>Posts</th>
                  <th className='p-2'>Status</th>
                </tr>
              </thead>
              <tbody>
                {accounts.collected_accounts.map((a) => (
                  <tr key={a.reference_id} className='border-b'>
                    <td className='p-2 font-mono text-xs'>
                      {a.reference_id}
                    </td>
                    <td className='p-2'>{a.platform}</td>
                    <td className='p-2 font-medium'>{a.username}</td>
                    <td className='p-2'>{a.post_count}</td>
                    <td className='p-2'>
                      <Badge variant='outline' className='text-xs'>
                        {a.collection_status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Limitations */}
      <Card>
        <CardHeader className='pb-3'>
          <CardTitle className='flex items-center gap-2 text-base'>
            <AlertTriangle className='size-4 text-amber-500' />
            Limitations ({limitations.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ul className='space-y-2 text-sm text-muted-foreground'>
            {limitations.map((l, i) => (
              <li key={i} className='flex items-start gap-2'>
                <span className='mt-1.5 size-1.5 shrink-0 rounded-full bg-amber-500' />
                {l}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {/* Confidence framework */}
      <Card>
        <CardHeader className='pb-3'>
          <CardTitle className='text-base'>Confidence Framework</CardTitle>
        </CardHeader>
        <CardContent className='space-y-3'>
          <div className='space-y-2 text-sm'>
            {Object.entries(confidence.band_definitions).map(([band, def]) => (
              <div key={band} className='flex items-start gap-3'>
                <Badge
                  className={cn(
                    'mt-0.5 text-xs text-white',
                    band === 'High' && 'bg-green-600 dark:bg-green-700',
                    band === 'Medium' && 'bg-amber-500 dark:bg-amber-600',
                    band === 'Low' && 'bg-slate-500 dark:bg-slate-600'
                  )}
                >
                  {band}
                </Badge>
                <span className='text-muted-foreground'>{def}</span>
              </div>
            ))}
          </div>
          <p className='text-xs italic text-muted-foreground'>
            {confidence.disclaimer}
          </p>
        </CardContent>
      </Card>

      {/* Intelligence section (if available) */}
      {intelligence && (
        <Card>
          <CardHeader className='pb-3'>
            <CardTitle className='flex items-center gap-2 text-base'>
              Executive Briefing
              <Badge variant='secondary' className='text-xs'>
                AI-Assisted
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className='space-y-3'>
            <p className='text-xs italic text-amber-600 dark:text-amber-400'>
              {intelligence.disclaimer}
            </p>
            <p className='text-sm leading-relaxed'>
              {intelligence.narrative}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Footer */}
      <p className='text-center text-xs text-muted-foreground'>
        <Clock className='mr-1 inline-block size-3' />
        Data captured at: {new Date(meta.generated_at).toLocaleString()} —
        Report methodology v{meta.methodology_version}
      </p>
    </div>
  )
}

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className='rounded-md border p-3 text-center'>
      <p className='text-2xl font-bold'>{value}</p>
      <p className='text-xs text-muted-foreground'>{label}</p>
    </div>
  )
}
