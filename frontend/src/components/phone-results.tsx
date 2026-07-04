import { Phone } from 'lucide-react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'

interface Lookup {
  id: number
  input_value?: string
  result?: Record<string, unknown>
}

interface Props {
  lookup: Lookup
}

function InfoRow({
  label,
  value,
  sub,
  variant,
}: {
  label: string
  value?: string | null
  sub?: string | null
  variant?: 'success' | 'danger' | 'default'
}) {
  if (value == null) return null
  return (
    <div className='flex items-center justify-between py-1.5'>
      <span className='text-sm text-muted-foreground'>{label}</span>
      <span
        className={`text-sm font-medium ${
          variant === 'success'
            ? 'text-primary'
            : variant === 'danger'
              ? 'text-destructive'
              : ''
        }`}
      >
        {value}
        {sub && (
          <span className='ml-1 text-xs font-normal text-muted-foreground'>
            ({sub})
          </span>
        )}
      </span>
    </div>
  )
}

export function PhoneResults({ lookup }: Props) {
  const r = (lookup.result || {}) as Record<string, unknown>
  const phoneNumber = String(r.phone_number ?? lookup.input_value ?? '')

  return (
    <div className='overflow-hidden rounded-lg border bg-card'>
      {/* Header */}
      <div className='flex items-center gap-3 border-b bg-muted/30 px-4 py-3'>
        <div className='flex h-8 w-8 items-center justify-center rounded-full bg-primary/10'>
          <Phone className='h-4 w-4 text-primary' />
        </div>
        <div>
          <p className='text-sm font-medium'>Phone Intelligence</p>
          <p className='font-mono text-xs text-muted-foreground'>
            {phoneNumber}
          </p>
        </div>
        {r.valid != null && (
          <Badge
            variant={(r.valid as boolean) ? 'default' : 'destructive'}
            className='ml-auto'
          >
            {(r.valid as boolean) ? 'Valid' : 'Invalid'}
          </Badge>
        )}
      </div>

      {/* Carrier Section */}
      <div className='px-4 py-3'>
        <p className='mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
          Carrier Information
        </p>
        <div className='grid grid-cols-2 gap-x-8'>
          <InfoRow label='Line Type' value={r.line_type as string} />
          <InfoRow label='Carrier' value={r.carrier as string} />
          <InfoRow
            label='Country'
            value={r.country_name as string}
            sub={r.country_code as string}
          />
          <InfoRow label='Region' value={r.location as string} />
        </div>
      </div>

      <Separator />

      {/* Messaging Apps */}
      <div className='grid grid-cols-1 divide-y sm:grid-cols-2 sm:divide-x sm:divide-y-0'>
        {/* Telegram */}
        <div className='px-4 py-3'>
          <p className='mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
            Telegram
          </p>
          {r.telegram_user_id ? (
            <div className='flex items-center gap-3'>
              <Avatar className='h-9 w-9'>
                {!!r.telegram_profile_photo_url && (
                  <AvatarImage src={r.telegram_profile_photo_url as string} />
                )}
                <AvatarFallback className='text-xs'>TG</AvatarFallback>
              </Avatar>
              <div>
                <p className='text-sm font-medium'>
                  {String(r.telegram_display_name ?? 'Unknown')}
                </p>
                {!!r.telegram_username && (
                  <a
                    href={`https://t.me/${r.telegram_username}`}
                    target='_blank'
                    rel='noopener noreferrer'
                    className='text-xs text-primary hover:underline'
                  >
                    @{String(r.telegram_username)}
                  </a>
                )}
              </div>
            </div>
          ) : (
            <p className='text-sm text-muted-foreground'>
              {r.telegram_registered === false
                ? 'Not registered'
                : 'Not checked'}
            </p>
          )}
        </div>

        {/* WhatsApp */}
        <div className='px-4 py-3'>
          <p className='mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
            WhatsApp
          </p>
          {r.whatsapp_registered ? (
            <div className='flex items-center gap-3'>
              <Avatar className='h-9 w-9'>
                {!!r.whatsapp_profile_photo_url && (
                  <AvatarImage
                    src={r.whatsapp_profile_photo_url as string}
                  />
                )}
                <AvatarFallback className='text-xs'>WA</AvatarFallback>
              </Avatar>
              <div>
                <p className='text-sm font-medium'>
                  {String(r.whatsapp_display_name ?? '—')}
                </p>
                {!!r.whatsapp_about && (
                  <p className='line-clamp-1 text-xs text-muted-foreground'>
                    {String(r.whatsapp_about)}
                  </p>
                )}
              </div>
            </div>
          ) : (
            <p className='text-sm text-muted-foreground'>
              {r.whatsapp_registered === false
                ? 'Not registered'
                : 'Not checked'}
            </p>
          )}
        </div>
      </div>

      {/* Web mentions */}
      {Array.isArray(r.web_mentions) && r.web_mentions.length > 0 && (
        <>
          <Separator />
          <div className='px-4 py-3'>
            <div className='mb-2 flex items-center gap-2'>
              <p className='text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
                Web Mentions
              </p>
              <Badge variant='secondary'>{r.web_mentions.length}</Badge>
            </div>
            <div className='space-y-2'>
              {(r.web_mentions as Array<Record<string, string>>).map(
                (m, i) => (
                  <div key={i}>
                    <a
                      href={m.url}
                      target='_blank'
                      rel='noopener noreferrer'
                      className='text-sm text-primary hover:underline'
                    >
                      {m.title || m.url}
                    </a>
                    {m.snippet && (
                      <p className='line-clamp-1 text-xs text-muted-foreground'>
                        {m.snippet}
                      </p>
                    )}
                  </div>
                )
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
