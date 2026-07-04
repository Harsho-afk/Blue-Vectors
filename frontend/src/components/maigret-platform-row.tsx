import { useState } from 'react'
import { Loader2, ExternalLink, Import } from 'lucide-react'
import { API } from '@/lib/aria-api'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

interface Platform {
  platform: string
  url: string
  status?: string
  tags?: string[]
  parsed_data?: {
    display_name?: string
    bio?: string
    avatar_url?: string
    location?: string
    followers?: number
  }
  lead_score?: number
  lead_band?: 'high' | 'medium' | 'low' | 'noise'
  lead_reasons?: string[]
}

interface Props {
  platform: Platform
  caseId: string
  searchedUsername: string
  onImported?: () => void
}

const BAND_STYLES: Record<
  string,
  { bg: string; text: string; label: string }
> = {
  high: {
    bg: 'bg-emerald-500/15 border-emerald-500/30',
    text: 'text-emerald-600 dark:text-emerald-400',
    label: 'Strong',
  },
  medium: {
    bg: 'bg-amber-500/15 border-amber-500/30',
    text: 'text-amber-600 dark:text-amber-400',
    label: 'Medium',
  },
  low: {
    bg: 'bg-zinc-500/15 border-zinc-500/30',
    text: 'text-zinc-500',
    label: 'Weak',
  },
  noise: {
    bg: 'bg-zinc-500/10 border-zinc-500/20',
    text: 'text-zinc-400',
    label: 'Noise',
  },
}

export function MaigretPlatformRow({
  platform,
  caseId,
  searchedUsername,
  onImported,
}: Props) {
  const [isImporting, setIsImporting] = useState(false)
  const [isImported, setIsImported] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const parsed = platform.parsed_data || {}
  const band = platform.lead_band || 'noise'
  const style = BAND_STYLES[band] || BAND_STYLES.noise

  const handleImport = async () => {
    setIsImporting(true)
    setError(null)
    try {
      const res = await fetch(
        `${API}/api/cases/${caseId}/osint/import-account`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            platform: platform.platform.toLowerCase(),
            username: searchedUsername,
            url: platform.url,
            display_name: parsed.display_name || null,
            bio: parsed.bio || null,
            avatar_url: parsed.avatar_url || null,
            location: parsed.location || null,
          }),
        }
      )
      if (!res.ok) {
        const detail = await res
          .json()
          .then((d) => d.detail)
          .catch(() => res.statusText)
        throw new Error(detail)
      }
      setIsImported(true)
      onImported?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import failed')
    } finally {
      setIsImporting(false)
    }
  }

  return (
    <div className={`flex items-start gap-3 rounded-lg border p-3 ${style.bg}`}>
      <Avatar className='h-8 w-8'>
        {parsed.avatar_url && <AvatarImage src={parsed.avatar_url} />}
        <AvatarFallback className='text-xs'>
          {platform.platform[0].toUpperCase()}
        </AvatarFallback>
      </Avatar>

      <div className='min-w-0 flex-1'>
        <div className='flex items-center gap-2'>
          <span className='text-sm font-medium'>{platform.platform}</span>
          {parsed.display_name && (
            <span className='text-xs text-muted-foreground'>
              {parsed.display_name}
            </span>
          )}
          <Badge
            variant='outline'
            className={`ml-auto text-[10px] px-1.5 py-0 ${style.text}`}
          >
            {style.label} {platform.lead_score != null ? `(${platform.lead_score})` : ''}
          </Badge>
        </div>
        {parsed.bio && (
          <p className='mt-0.5 line-clamp-1 text-xs text-muted-foreground'>
            {parsed.bio}
          </p>
        )}
        <div className='mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground'>
          {parsed.location && <span>{parsed.location}</span>}
          {parsed.followers != null && (
            <span>{parsed.followers.toLocaleString()} followers</span>
          )}
        </div>
        {platform.lead_reasons && platform.lead_reasons.length > 0 && (
          <div className='mt-1 flex flex-wrap gap-1'>
            {platform.lead_reasons.map((reason) => (
              <span
                key={reason}
                className='rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground'
              >
                {reason}
              </span>
            ))}
          </div>
        )}
        {error && (
          <span className='mt-0.5 text-xs text-destructive'>{error}</span>
        )}
      </div>

      <div className='flex shrink-0 gap-1'>
        <Button variant='ghost' size='sm' asChild>
          <a
            href={platform.url}
            target='_blank'
            rel='noopener noreferrer'
          >
            <ExternalLink className='h-3 w-3' />
            Open
          </a>
        </Button>
        <Button
          variant={isImported ? 'secondary' : 'outline'}
          size='sm'
          disabled={isImporting || isImported}
          onClick={handleImport}
        >
          {isImported ? (
            'Imported'
          ) : isImporting ? (
            <>
              <Loader2 className='h-3 w-3 animate-spin' />
              Importing...
            </>
          ) : (
            <>
              <Import className='h-3 w-3' />
              Import
            </>
          )}
        </Button>
      </div>
    </div>
  )
}
