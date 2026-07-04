import { useState, useMemo } from 'react'
import {
  ChevronDown,
  ChevronRight,
  Globe,
  Link2,
  Star,
  AlertTriangle,
  Eye,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { MaigretPlatformRow } from './maigret-platform-row'

interface PlatformEntry {
  platform: string
  url: string
  parsed_data?: Record<string, unknown>
  lead_score?: number
  lead_band?: 'high' | 'medium' | 'low' | 'noise'
  lead_reasons?: string[]
  tags?: string[]
}

interface Lookup {
  id: number
  input_value?: string
  result?: {
    username?: string
    total_found?: number
    error?: string
    categories?: Record<string, PlatformEntry[]>
    linked_accounts?: Array<{
      username: string
      source_platform: string
    }>
    lead_summary?: {
      high?: number
      medium?: number
      low?: number
      noise?: number
    }
  }
}

interface Props {
  lookup: Lookup
  caseId: string
  onAccountImported?: () => void
}

const BAND_CONFIG = [
  {
    key: 'high' as const,
    label: 'Recommended Leads',
    icon: Star,
    badgeVariant: 'default' as const,
    badgeClass: 'bg-emerald-600',
    defaultOpen: true,
  },
  {
    key: 'medium' as const,
    label: 'Worth Investigating',
    icon: Eye,
    badgeVariant: 'default' as const,
    badgeClass: 'bg-amber-600',
    defaultOpen: true,
  },
  {
    key: 'low' as const,
    label: 'Weak Leads',
    icon: AlertTriangle,
    badgeVariant: 'secondary' as const,
    badgeClass: '',
    defaultOpen: false,
  },
  {
    key: 'noise' as const,
    label: 'Unverified / Likely False Positives',
    icon: AlertTriangle,
    badgeVariant: 'secondary' as const,
    badgeClass: '',
    defaultOpen: false,
  },
]

export function MaigretResults({ lookup, caseId, onAccountImported }: Props) {
  const result = lookup.result || {}
  const categories = result.categories || {}
  const linkedAccounts = result.linked_accounts || []
  const summary = result.lead_summary || {}

  const [expandedBands, setExpandedBands] = useState<Set<string>>(() => {
    const initial = new Set<string>()
    for (const bc of BAND_CONFIG) {
      if (bc.defaultOpen) initial.add(bc.key)
    }
    return initial
  })

  const platformsByBand = useMemo(() => {
    const bands: Record<string, PlatformEntry[]> = {
      high: [],
      medium: [],
      low: [],
      noise: [],
    }

    for (const platforms of Object.values(categories)) {
      for (const entry of platforms) {
        const band = entry.lead_band || 'noise'
        bands[band].push(entry)
      }
    }

    for (const band of Object.values(bands)) {
      band.sort((a, b) => (b.lead_score || 0) - (a.lead_score || 0))
    }

    return bands
  }, [categories])

  const toggleBand = (key: string) => {
    setExpandedBands((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const totalStrong = (summary.high || 0) + (summary.medium || 0)
  const totalWeak = (summary.low || 0) + (summary.noise || 0)

  return (
    <div className='overflow-hidden rounded-lg border bg-card'>
      {/* Header */}
      <div className='flex items-center gap-3 border-b bg-muted/30 px-4 py-3'>
        <div className='flex h-8 w-8 items-center justify-center rounded-full bg-primary/10'>
          <Globe className='h-4 w-4 text-primary' />
        </div>
        <div className='min-w-0 flex-1'>
          <p className='text-sm font-medium'>Username Search</p>
          <p className='font-mono text-xs text-muted-foreground'>
            {result.username || lookup.input_value}
          </p>
        </div>
        <div className='flex shrink-0 items-center gap-2'>
          <Badge variant='default'>
            {result.total_found || 0} found
          </Badge>
          {totalStrong > 0 && (
            <Badge variant='default' className='bg-emerald-600'>
              {totalStrong} lead{totalStrong !== 1 ? 's' : ''}
            </Badge>
          )}
          {totalWeak > 0 && (
            <Badge variant='secondary'>
              {totalWeak} weak
            </Badge>
          )}
        </div>
      </div>

      {result.error && (
        <div className='border-b px-4 py-2 text-xs text-muted-foreground'>
          {result.error}
        </div>
      )}

      {/* Band-grouped results */}
      {BAND_CONFIG.map((config) => {
        const platforms = platformsByBand[config.key]
        if (!platforms || platforms.length === 0) return null

        const isExpanded = expandedBands.has(config.key)
        const Icon = config.icon

        return (
          <div key={config.key} className='border-b last:border-b-0'>
            <button
              onClick={() => toggleBand(config.key)}
              className='flex w-full items-center gap-2 px-4 py-2.5 text-left transition-colors hover:bg-muted/30'
            >
              {isExpanded ? (
                <ChevronDown className='h-4 w-4 shrink-0 text-muted-foreground' />
              ) : (
                <ChevronRight className='h-4 w-4 shrink-0 text-muted-foreground' />
              )}
              <Icon className='h-4 w-4 shrink-0 text-muted-foreground' />
              <span className='flex-1 text-sm font-medium'>
                {config.label}
              </span>
              <Badge
                variant={config.badgeVariant}
                className={config.badgeClass}
              >
                {platforms.length}
              </Badge>
            </button>

            {isExpanded && (
              <div className='space-y-2 px-4 pb-3'>
                {platforms.map((platform) => (
                  <MaigretPlatformRow
                    key={platform.platform}
                    platform={platform as any}
                    caseId={caseId}
                    searchedUsername={
                      result.username || lookup.input_value || ''
                    }
                    onImported={onAccountImported}
                  />
                ))}
              </div>
            )}
          </div>
        )
      })}

      {/* Linked accounts */}
      {linkedAccounts.length > 0 && (
        <>
          <Separator />
          <div className='px-4 py-3'>
            <div className='mb-2 flex items-center gap-2'>
              <Link2 className='h-3 w-3 text-muted-foreground' />
              <p className='text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
                Discovered Linked Accounts
              </p>
              <Badge variant='secondary'>{linkedAccounts.length}</Badge>
            </div>
            <div className='space-y-1'>
              {linkedAccounts.map((linked, i) => (
                <div
                  key={linked.username || i}
                  className='flex items-center gap-2 text-sm'
                >
                  <span className='font-mono'>{linked.username}</span>
                  <span className='text-xs text-muted-foreground'>
                    via {linked.source_platform}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
