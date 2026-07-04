import { useState } from 'react'
import { Loader2, ExternalLink, Import } from 'lucide-react'
import { API } from '@/lib/aria-api'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
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
}

interface Props {
  platform: Platform
  caseId: string
  searchedUsername: string
  onImported?: () => void
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
    <div className='flex items-start gap-3 rounded-lg border p-3'>
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
        </div>
        {parsed.bio && (
          <p className='mt-0.5 line-clamp-1 text-xs text-muted-foreground'>
            {parsed.bio}
          </p>
        )}
        <div className='mt-0.5 flex items-center gap-2 text-xs text-muted-foreground'>
          {parsed.location && <span>{parsed.location}</span>}
          {parsed.followers != null && (
            <span>{parsed.followers.toLocaleString()} followers</span>
          )}
        </div>
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
