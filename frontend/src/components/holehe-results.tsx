import { ExternalLink, Mail } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

interface Site {
  name: string
  domain: string
  url?: string
  method?: string
  emailrecovery?: string | null
  phoneNumber?: string | null
}

interface Lookup {
  id: number
  input_value?: string
  result?: {
    email?: string
    total_checked?: number
    total_found?: number
    sites?: Site[]
  }
}

interface Props {
  lookup: Lookup
}

export function HoleheResults({ lookup }: Props) {
  const r = lookup.result || {}
  const email = r.email || lookup.input_value || ''
  const sites = r.sites || []
  const totalChecked = r.total_checked || 0

  if (sites.length === 0) {
    return (
      <div className='rounded-lg border bg-card px-4 py-3'>
        <div className='flex items-center gap-2 text-sm text-muted-foreground'>
          <Mail className='h-4 w-4' />
          <span className='font-mono'>{email}</span>
          <span>— not found on any of {totalChecked} sites checked</span>
        </div>
      </div>
    )
  }

  return (
    <div className='overflow-hidden rounded-lg border bg-card'>
      <div className='flex items-center gap-3 border-b bg-muted/30 px-4 py-3'>
        <div className='flex h-8 w-8 items-center justify-center rounded-full bg-primary/10'>
          <Mail className='h-4 w-4 text-primary' />
        </div>
        <div>
          <p className='text-sm font-medium'>Email Account Discovery</p>
          <p className='font-mono text-xs text-muted-foreground'>{email}</p>
        </div>
        <div className='ml-auto flex items-center gap-2'>
          <Badge variant='secondary'>{totalChecked} checked</Badge>
          <Badge variant='default'>{sites.length} found</Badge>
        </div>
      </div>

      <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 p-3'>
        {sites.map((site) => (
          <a
            key={site.name}
            href={site.url || `https://${site.domain}`}
            target='_blank'
            rel='noopener noreferrer'
            className='flex items-center gap-2.5 rounded-md border px-3 py-2 text-sm transition-colors hover:bg-muted/50'
          >
            <img
              src={`https://www.google.com/s2/favicons?domain=${site.domain}&sz=32`}
              alt=''
              className='h-4 w-4 shrink-0 rounded-sm'
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none'
              }}
            />
            <div className='min-w-0 flex-1'>
              <p className='truncate font-medium capitalize'>{site.name}</p>
              <p className='truncate text-xs text-muted-foreground'>
                {site.domain}
                {site.method && (
                  <span className='ml-1 opacity-70'>· {site.method}</span>
                )}
              </p>
            </div>
            <ExternalLink className='h-3 w-3 shrink-0 text-muted-foreground' />
          </a>
        ))}
      </div>

      {sites.some((s) => s.emailrecovery || s.phoneNumber) && (
        <div className='border-t px-4 py-2'>
          <p className='mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
            Recovery Info Found
          </p>
          <div className='space-y-1'>
            {sites
              .filter((s) => s.emailrecovery || s.phoneNumber)
              .map((s) => (
                <div key={s.name} className='text-xs text-muted-foreground'>
                  <span className='font-medium text-foreground capitalize'>{s.name}</span>
                  {s.emailrecovery && <span> · recovery email: {s.emailrecovery}</span>}
                  {s.phoneNumber && <span> · phone: {s.phoneNumber}</span>}
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}
