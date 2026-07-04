import { useState } from 'react'
import { ChevronDown, ChevronRight, Globe, Link2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { MaigretPlatformRow } from './maigret-platform-row'

const CATEGORY_ORDER = [
  'social_media',
  'developer',
  'gaming',
  'streaming',
  'professional',
  'creative',
  'messaging',
  'shopping',
  'other',
]

const CATEGORY_DISPLAY: Record<string, string> = {
  social_media: 'Social Media',
  developer: 'Developer & Tech',
  gaming: 'Gaming',
  streaming: 'Streaming & Media',
  professional: 'Professional',
  creative: 'Creative & Art',
  messaging: 'Messaging',
  shopping: 'Shopping & Finance',
  other: 'Other Platforms',
}

interface Lookup {
  id: number
  input_value?: string
  result?: {
    username?: string
    total_found?: number
    error?: string
    categories?: Record<
      string,
      Array<{
        platform: string
        url: string
        parsed_data?: Record<string, unknown>
      }>
    >
    linked_accounts?: Array<{
      username: string
      source_platform: string
    }>
  }
}

interface Props {
  lookup: Lookup
  caseId: string
  onAccountImported?: () => void
}

export function MaigretResults({ lookup, caseId, onAccountImported }: Props) {
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(
    new Set()
  )

  const result = lookup.result || {}
  const categories = result.categories || {}
  const linkedAccounts = result.linked_accounts || []

  const nonEmptyCategories = CATEGORY_ORDER.filter(
    (k) => categories[k] && categories[k].length > 0
  )

  const toggleCategory = (key: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  return (
    <div className='overflow-hidden rounded-lg border bg-card'>
      {/* Header */}
      <div className='flex items-center gap-3 border-b bg-muted/30 px-4 py-3'>
        <div className='flex h-8 w-8 items-center justify-center rounded-full bg-primary/10'>
          <Globe className='h-4 w-4 text-primary' />
        </div>
        <div className='min-w-0 flex-1'>
          <p className='text-sm font-medium'>
            Username Search
          </p>
          <p className='font-mono text-xs text-muted-foreground'>
            {result.username || lookup.input_value}
          </p>
        </div>
        <div className='flex shrink-0 items-center gap-2'>
          <Badge variant='default'>
            {result.total_found || 0} found
          </Badge>
          <Badge variant='secondary'>
            {nonEmptyCategories.length} categor
            {nonEmptyCategories.length !== 1 ? 'ies' : 'y'}
          </Badge>
        </div>
      </div>

      {result.error && (
        <div className='border-b px-4 py-2 text-xs text-muted-foreground'>
          {result.error}
        </div>
      )}

      {/* Category accordions */}
      {CATEGORY_ORDER.map((categoryKey) => {
        const platforms = categories[categoryKey]
        if (!platforms || platforms.length === 0) return null

        const isExpanded = expandedCategories.has(categoryKey)

        return (
          <div key={categoryKey} className='border-b last:border-b-0'>
            <button
              onClick={() => toggleCategory(categoryKey)}
              className='flex w-full items-center gap-2 px-4 py-2.5 text-left transition-colors hover:bg-muted/30'
            >
              {isExpanded ? (
                <ChevronDown className='h-4 w-4 shrink-0 text-muted-foreground' />
              ) : (
                <ChevronRight className='h-4 w-4 shrink-0 text-muted-foreground' />
              )}
              <span className='flex-1 text-sm font-medium'>
                {CATEGORY_DISPLAY[categoryKey] || categoryKey}
              </span>
              <Badge variant='secondary'>{platforms.length}</Badge>
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
