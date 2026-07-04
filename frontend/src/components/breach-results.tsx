import { CheckCircle, ShieldAlert } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

interface Lookup {
  id: number
  input_value?: string
  result?: {
    email?: string
    total_breaches?: number
    error?: string
    is_mock?: boolean
    breaches?: Array<{
      name: string
      breach_date?: string
      date?: string
      data_classes?: string[]
    }>
  }
}

interface Props {
  lookup: Lookup
}

export function BreachResults({ lookup }: Props) {
  const result = lookup.result || {}
  const breaches = result.breaches || []
  const email = result.email || lookup.input_value || ''
  const total = result.total_breaches ?? breaches.length

  return (
    <div className='overflow-hidden rounded-lg border bg-card'>
      {/* Header */}
      <div className='flex items-center gap-3 border-b bg-muted/30 px-4 py-3'>
        <div
          className={`flex h-8 w-8 items-center justify-center rounded-full ${
            total > 0
              ? 'bg-destructive/10'
              : 'bg-primary/10'
          }`}
        >
          {total > 0 ? (
            <ShieldAlert className='h-4 w-4 text-destructive' />
          ) : (
            <CheckCircle className='h-4 w-4 text-primary' />
          )}
        </div>
        <div className='min-w-0 flex-1'>
          <p className='text-sm font-medium'>Breach Check</p>
          <p className='truncate font-mono text-xs text-muted-foreground'>
            {email}
          </p>
        </div>
        <div className='flex shrink-0 items-center gap-2'>
          {result.is_mock && (
            <Badge variant='outline' className='text-xs'>
              DEMO
            </Badge>
          )}
          {total > 0 ? (
            <Badge variant='destructive'>
              {total} breach{total !== 1 ? 'es' : ''}
            </Badge>
          ) : (
            <Badge variant='default'>Clean</Badge>
          )}
        </div>
      </div>

      {result.error && (
        <div className='border-b px-4 py-2 text-xs text-muted-foreground'>
          {result.error}
        </div>
      )}

      {total === 0 && !result.error && (
        <div className='flex items-center gap-2 px-4 py-4 text-sm text-muted-foreground'>
          <CheckCircle className='h-4 w-4 text-primary' />
          No breaches found for this email address.
        </div>
      )}

      {breaches.length > 0 && (
        <div className='px-4 py-3'>
          <div className='space-y-2'>
            {breaches.map((breach, i) => (
              <div
                key={breach.name || i}
                className='rounded-lg border p-3'
              >
                <div className='flex items-center justify-between'>
                  <span className='text-sm font-medium'>{breach.name}</span>
                  {(breach.breach_date || breach.date) && (
                    <span className='text-xs text-muted-foreground'>
                      {breach.breach_date || breach.date}
                    </span>
                  )}
                </div>
                {breach.data_classes && breach.data_classes.length > 0 && (
                  <div className='mt-2 flex flex-wrap gap-1'>
                    {breach.data_classes.map((dc) => (
                      <Badge
                        key={dc}
                        variant='secondary'
                        className='text-xs'
                      >
                        {dc}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
